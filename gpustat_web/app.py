"""
gpustat.web

@author Jongwook Choi
"""

import sys
import traceback

import asyncio
import asyncssh
import aiohttp

from datetime import datetime
from collections import OrderedDict
from getpass import getpass

from termcolor import cprint, colored
from aiohttp import web
import aiohttp_jinja2 as aiojinja2

import os
__PATH__ = os.path.abspath(os.path.dirname(__file__))


###############################################################################
# Background workers to collect information from nodes
###############################################################################

class Context(object):
    '''The global context object.'''
    def __init__(self):
        self.host_status = OrderedDict()
        self.interval = 5.0

    def host_set_message(self, host, msg):
        self.host_status[host] = colored(f"({host}) ", 'white') + msg + '\n'


context = Context()


# async handlers to collect gpu stats
async def run_client(host, exec_cmd, poll_delay=None, timeout=30.0,
                     name_length=None, verbose=False, username=None, password=None):
    L = name_length or 0
    if poll_delay is None:
        poll_delay = context.interval

    async def _loop_body():
        # establish a SSH connection.
        async with asyncssh.connect(host, username=username, password=password) as conn:
            cprint(f"[{host:<{L}}] SSH connection established!", attrs=['bold'])

            while True:
                if False: #verbose: XXX DEBUG
                    print(f"[{host:<{L}}] querying... ")

                result = await asyncio.wait_for(conn.run(exec_cmd), timeout=timeout)

                now = datetime.now().strftime('%Y/%m/%d-%H:%M:%S.%f')
                if result.exit_status != 0:
                    cprint(f"[{now} [{host:<{L}}] error, exitcode={result.exit_status}", color='red')
                    context.host_set_message(host, colored(f'error, exitcode={result.exit_status}', 'red'))
                else:
                    if verbose:
                        cprint(f"[{now} [{host:<{L}}] OK from gpustat ({len(result.stdout)} bytes)", color='cyan')
                    # update data
                    context.host_status[host] = result.stdout

                # wait for a while...
                await asyncio.sleep(poll_delay)

    while True:
        try:
            # start SSH connection, or reconnect if it was disconnected
            await _loop_body()

        except asyncio.CancelledError:
            cprint(f"[{host:<{L}}] Closed as being cancelled.", attrs=['bold'])
            break
        except (asyncio.TimeoutError) as ex:
            # timeout (retry)
            cprint(f"Timeout after {timeout} sec: {host}", color='red')
            context.host_set_message(host, colored(f"Timeout after {timeout} sec", 'red'))
        except (asyncssh.misc.DisconnectError, asyncssh.misc.ChannelOpenError, OSError) as ex:
            # error or disconnected (retry)
            cprint(f"Disconnected : {host}, {str(ex)}", color='red')
            context.host_set_message(host, colored(str(ex), 'red'))
        except Exception as e:
            # A general exception unhandled, throw
            cprint(f"[{host:<{L}}] {e}", color='red')
            context.host_set_message(host, colored(f"{type(e).__name__}: {e}", 'red'))
            cprint(traceback.format_exc())
            raise

        # retry upon timeout/disconnected, etc.
        cprint(f"[{host:<{L}}] Disconnected, retrying in {poll_delay} sec...", color='yellow')
        await asyncio.sleep(poll_delay)


async def spawn_clients(hosts, exec_cmd, username, password, verbose=False):
    # initial response
    for host in hosts:
        context.host_set_message(host, "Loading ...")

    name_length = max(len(host) for host in hosts)

    # launch all clients parallel
    await asyncio.gather(*[
        run_client(host, exec_cmd, verbose=verbose, name_length=name_length, username=username, password=password) for host in hosts
    ])


###############################################################################
# webserver handlers.
###############################################################################

# monkey-patch ansi2html scheme. TODO: better color codes
import ansi2html
scheme = 'solarized'
ansi2html.style.SCHEME[scheme] = list(ansi2html.style.SCHEME[scheme])
ansi2html.style.SCHEME[scheme][0] = '#555555'
ansi_conv = ansi2html.Ansi2HTMLConverter(dark_bg=True, scheme=scheme)


def render_gpustat_body():
    body = ''
    for host, status in context.host_status.items():
        if not status:
            continue
        body += status
    return ansi_conv.convert(body, full=False)


async def handler(request):
    '''Renders the html page.'''

    data = dict(
        ansi2html_headers=ansi_conv.produce_headers().replace('\n', ' '),
        http_host=request.host,
        interval=int(context.interval * 1000)
    )
    response = aiojinja2.render_template('index.html', request, data)
    response.headers['Content-Language'] = 'en'
    return response


async def websocket_handler(request):
    print("INFO: Websocket connection from {} established".format(request.remote))

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async def _handle_websocketmessage(msg):
        if msg.data == 'close':
            await ws.close()
        else:
            # send the rendered HTML body as a websocket message.
            body = render_gpustat_body()
            await ws.send_str(body)

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.CLOSE:
            break
        elif msg.type == aiohttp.WSMsgType.TEXT:
            await _handle_websocketmessage(msg)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            cprint("Websocket connection closed with exception %s" % ws.exception(), color='red')

    print("INFO: Websocket connection from {} closed".format(request.remote))
    return ws

###############################################################################
# app factory and entrypoint.
###############################################################################

def create_app(loop, username, password, hosts=['localhost'], exec_cmd=None, verbose=True):
    if not exec_cmd:
        exec_cmd = 'gpustat --color'

    app = web.Application()
    app.router.add_get('/', handler)
    app.add_routes([web.get('/ws', websocket_handler)])

    async def start_background_tasks(app):
        app._tasks = app.loop.create_task(spawn_clients(hosts, exec_cmd, username, password, verbose=verbose))
        await asyncio.sleep(0.1)
    app.on_startup.append(start_background_tasks)

    async def shutdown_background_tasks(app):
        cprint(f"... Terminating the application", color='yellow')
        app._tasks.cancel()
    app.on_shutdown.append(shutdown_background_tasks)

    # jinja2 setup
    import jinja2
    aiojinja2.setup(app,
                    loader=jinja2.FileSystemLoader(
                        os.path.join(__PATH__, 'template'))
                    )
    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hosts', nargs='*')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--port', type=int, default=48109)
    parser.add_argument('--interval', type=float, default=5.0)
    parser.add_argument('--exec', type=str,
                        default="gpustat --color --gpuname-width 25",
                        help="command-line to execute (e.g. gpustat --color --gpuname-width 25)",
                        )
    parser.add_argument('--username', type=str, default=None)
    parser.add_argument('--password', action='store_true', 
                        help="password for ssh authentication")
    args = parser.parse_args()

    if args.password:
        password = getpass()
    else:
        password = None

    hosts = args.hosts or ['localhost']
    cprint(f"Hosts : {hosts}", color='green')
    cprint(f"Cmd   : {args.exec}", color='yellow')

    if args.interval > 0.1:
        context.interval = args.interval

    loop = asyncio.get_event_loop()
    app = create_app(loop, 
                     username=args.username,
                     password=password,
                     hosts=hosts,
                     exec_cmd=args.exec,
                     verbose=args.verbose)

    web.run_app(app, host='0.0.0.0', port=args.port)

if __name__ == '__main__':
    main()
