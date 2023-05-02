"""
gpustat.web


MIT License

Copyright (c) 2018-2020 Jongwook Choi (@wookayin)
"""

from typing import List, Tuple, Optional
import json
import re
import os
import sys
import traceback
import urllib
import ssl

import asyncio
import asyncssh
import aiohttp

from datetime import datetime
from collections import OrderedDict, Counter

from termcolor import cprint, colored
from aiohttp import web
import aiohttp_jinja2 as aiojinja2


__PATH__ = os.path.abspath(os.path.dirname(__file__))

DEFAULT_GPUSTAT_COMMAND = "gpustat --color --gpuname-width 25"

RE_ANSI = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

###############################################################################
# Background workers to collect information from nodes
###############################################################################

class Context(object):
    '''The global context object.'''
    def __init__(self):
        self.host_status = OrderedDict()
        self.interval = 5.0

    def host_set_message(self, hostname: str, msg: str):
        self.host_status[hostname] = colored(f"({hostname}) ", 'white') + msg + '\n'


context = Context()


async def run_client(hostname: str, exec_cmd: str, *, port=22,
                     poll_delay=None, timeout=30.0,
                     name_length=None, verbose=False):
    '''An async handler to collect gpustat through a SSH channel.'''
    L = name_length or 0
    if poll_delay is None:
        poll_delay = context.interval

    async def _loop_body():
        # establish a SSH connection.
        async with asyncssh.connect(hostname, port=port) as conn:
            cprint(f"[{hostname:<{L}}] SSH connection established!", attrs=['bold'])

            while True:
                if False: #verbose: XXX DEBUG
                    print(f"[{hostname:<{L}}] querying... ")

                result = await asyncio.wait_for(conn.run(exec_cmd), timeout=timeout)

                now = datetime.now().strftime('%Y/%m/%d-%H:%M:%S.%f')
                if result.exit_status != 0:
                    cprint(f"[{now} [{hostname:<{L}}] Error, exitcode={result.exit_status}", color='red')
                    cprint(result.stderr or '', color='red')
                    stderr_summary = (result.stderr or '').split('\n')[0]
                    context.host_set_message(hostname, colored(f'[exitcode {result.exit_status}] {stderr_summary}', 'red'))
                else:
                    if verbose:
                        cprint(f"[{now} [{hostname:<{L}}] OK from gpustat ({len(result.stdout)} bytes)", color='cyan')
                    # update data
                    context.host_status[hostname] = result.stdout

                # wait for a while...
                await asyncio.sleep(poll_delay)

    while True:
        try:
            # start SSH connection, or reconnect if it was disconnected
            await _loop_body()

        except asyncio.CancelledError:
            cprint(f"[{hostname:<{L}}] Closed as being cancelled.", attrs=['bold'])
            break
        except (asyncio.TimeoutError) as ex:
            # timeout (retry)
            cprint(f"Timeout after {timeout} sec: {hostname}", color='red')
            context.host_set_message(hostname, colored(f"Timeout after {timeout} sec", 'red'))
        except (asyncssh.misc.DisconnectError, asyncssh.misc.ChannelOpenError, OSError) as ex:
            # error or disconnected (retry)
            cprint(f"Disconnected : {hostname}, {str(ex)}", color='red')
            context.host_set_message(hostname, colored(str(ex), 'red'))
        except Exception as e:
            # A general exception unhandled, throw
            cprint(f"[{hostname:<{L}}] {e}", color='red')
            context.host_set_message(hostname, colored(f"{type(e).__name__}: {e}", 'red'))
            cprint(traceback.format_exc())
            raise

        # retry upon timeout/disconnected, etc.
        cprint(f"[{hostname:<{L}}] Disconnected, retrying in {poll_delay} sec...", color='yellow')
        await asyncio.sleep(poll_delay)


async def spawn_clients(hosts: List[str], exec_cmd: str, *,
                        default_port: int, verbose=False):
    '''Create a set of async handlers, one per host.'''

    def _parse_host_string(netloc: str) -> Tuple[str, Optional[int]]:
        """Parse a connection string (netloc) in the form of `HOSTNAME[:PORT]`
        and returns (HOSTNAME, PORT)."""
        pr = urllib.parse.urlparse('ssh://{}/'.format(netloc))
        assert pr.hostname is not None, netloc
        return (pr.hostname, pr.port)

    try:
        host_names, host_ports = zip(*(_parse_host_string(host) for host in hosts))

        # initial response
        for hostname in host_names:
            context.host_set_message(hostname, "Loading ...")

        name_length = max(len(hostname) for hostname in host_names)

        # launch all clients parallel
        await asyncio.gather(*[
            run_client(hostname, exec_cmd, port=port or default_port,
                    verbose=verbose, name_length=name_length)
            for (hostname, port) in zip(host_names, host_ports)
        ])
    except Exception as ex:
        # TODO: throw the exception outside and let aiohttp abort startup
        traceback.print_exc()
        cprint(colored("Error: An exception occured during the startup.", 'red'))


###############################################################################
# webserver handlers.
###############################################################################

# monkey-patch ansi2html scheme. TODO: better color codes
import ansi2html
scheme = 'solarized'
ansi2html.style.SCHEME[scheme] = list(ansi2html.style.SCHEME[scheme])
ansi2html.style.SCHEME[scheme][0] = '#555555'
ansi_conv = ansi2html.Ansi2HTMLConverter(dark_bg=True, scheme=scheme)


def render_gpustat_body(
    mode='html',   # mode: Literal['html'] | Literal['html_full'] | Literal['ansi']
    *,
    full_html: bool = False,
    nodes: Optional[List[str]] = None,
):
    body = ''
    for host, status in context.host_status.items():
        if not status:
            continue
        if nodes is not None and host not in nodes:
            continue
        body += status

    if mode == 'html':
        return ansi_conv.convert(body, full=full_html)
    elif mode == 'ansi':
        return body
    elif mode == 'plain':
        return RE_ANSI.sub('', body)
    else:
        raise ValueError(mode)


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


def _parse_querystring_list(value: Optional[str]) -> Optional[List[str]]:
    return value.strip().split(',') if value else None


def make_static_handler(content_type: str):

    async def handler(request: web.Request):
        # query string handling
        full: bool = request.query.get('full', '1').lower() in ("yes", "true", "1")
        nodes: Optional[List[str]] = _parse_querystring_list(request.query.get('nodes'))

        body = render_gpustat_body(mode=content_type,
                                   full_html=full,
                                   nodes=nodes)
        response = web.Response(body=body)
        response.headers['Content-Language'] = 'en'
        response.headers['Content-Type'] = f'text/{content_type}; charset=utf-8'
        return response

    return handler


async def websocket_handler(request):
    print("INFO: Websocket connection from {} established".format(request.remote))

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async def _handle_websocketmessage(msg):
        if msg.data == 'close':
            await ws.close()
        else:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                cprint(f"Malformed message from {request.remote}", color='yellow')
                return

            # send the rendered HTML body as a websocket message.
            nodes: Optional[List[str]] = _parse_querystring_list(payload.get('nodes'))
            body = render_gpustat_body(mode='html', full_html=False, nodes=nodes)
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

def create_app(*,
               hosts=['localhost'],
               default_port: int = 22,
               ssl_certfile: Optional[str] = None,
               ssl_keyfile: Optional[str] = None,
               exec_cmd: Optional[str] = None,
               verbose=True):
    if not exec_cmd:
        exec_cmd = DEFAULT_GPUSTAT_COMMAND

    app = web.Application()
    app.router.add_get('/', handler)
    app.add_routes([web.get('/ws', websocket_handler)])
    app.add_routes([web.get('/gpustat.html', make_static_handler('html'))])
    app.add_routes([web.get('/gpustat.ansi', make_static_handler('ansi'))])
    app.add_routes([web.get('/gpustat.txt', make_static_handler('plain'))])

    async def start_background_tasks(app):
        clients = spawn_clients(
            hosts, exec_cmd, default_port=default_port, verbose=verbose)
        # See #19 for why we need to this against aiohttp 3.5, 3.8, and 4.0
        loop = app.loop if hasattr(app, 'loop') else asyncio.get_event_loop()
        app['tasks'] = loop.create_task(clients)
        await asyncio.sleep(0.1)
    app.on_startup.append(start_background_tasks)

    async def shutdown_background_tasks(app):
        cprint(f"... Terminating the application", color='yellow')
        app['tasks'].cancel()
    app.on_shutdown.append(shutdown_background_tasks)

    # jinja2 setup
    import jinja2
    aiojinja2.setup(app,
                    loader=jinja2.FileSystemLoader(
                        os.path.join(__PATH__, 'template'))
                    )

    # SSL setup
    if ssl_certfile and ssl_keyfile:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=ssl_certfile,
                                    keyfile=ssl_keyfile)

        cprint(f"Using Secure HTTPS (SSL/TLS) server ...", color='green')
    else:
        ssl_context = None   # type: ignore
    return app, ssl_context


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hosts', nargs='*',
                        help='List of nodes. Syntax: HOSTNAME[:PORT]')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--port', type=int, default=48109,
                        help="Port number the web application will listen to. (Default: 48109)")
    parser.add_argument('--ssh-port', type=int, default=22,
                        help="Default SSH port to establish connection through. (Default: 22)")
    parser.add_argument('--interval', type=float, default=5.0,
                        help="Interval (in seconds) between two consecutive requests.")
    parser.add_argument('--ssl-certfile', type=str, default=None,
                        help="Path to the SSL certificate file (Optional, if want to run HTTPS server)")
    parser.add_argument('--ssl-keyfile', type=str, default=None,
                        help="Path to the SSL private key file (Optional, if want to run HTTPS server)")
    parser.add_argument('--exec', type=str,
                        default=DEFAULT_GPUSTAT_COMMAND,
                        help="command-line to execute (e.g. gpustat --color --gpuname-width 25)")
    args = parser.parse_args()

    hosts = args.hosts or ['localhost']
    cprint(f"Hosts : {hosts}", color='green')
    cprint(f"Cmd   : {args.exec}", color='yellow')

    if args.interval > 0.1:
        context.interval = args.interval

    app, ssl_context = create_app(
        hosts=hosts, default_port=args.ssh_port,
        ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile,
        exec_cmd=args.exec,
        verbose=args.verbose)

    web.run_app(app, host='0.0.0.0', port=args.port,
                ssl_context=ssl_context)

if __name__ == '__main__':
    main()
