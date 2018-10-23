"""
gpustat.web

@author Jongwook Choi
"""

import asyncio
import asyncssh
import sys
import traceback

from datetime import datetime
from collections import OrderedDict

from termcolor import cprint, colored
from aiohttp import web


# the global context object
class Context(object):
    def __init__(self):
        self.host_status = OrderedDict()

    def host_set_message(self, host, msg):
        self.host_status[host] = colored(f"({host}) ", 'white') + msg + '\n'


context = Context()


# async handlers to collect gpu stats
async def run_client(host, poll_delay=5.0, name_length=None, verbose=False):
    L = name_length or 0

    try:
        # establish a SSH connection.
        async with asyncssh.connect(host) as conn:
            print(f"[{host:<{L}}] connection established!")

            while True:
                if False: #verbose: XXX DEBUG
                    print(f"[{host:<{L}}] querying... ")

                result = await conn.run('gpustat --color --gpuname-width 25')

                now = datetime.now().strftime('%Y/%m/%d-%H:%M:%S.%f')
                if result.exit_status != 0:
                    cprint(f"[{now} [{host:<{L}}] error, exitcode={result.exit_status}", color='red')
                else:
                    if verbose:
                        cprint(f"[{now} [{host:<{L}}] OK from gpustat ({len(result.stdout)} bytes)", color='cyan')
                    # update data
                    context.host_status[host] = result.stdout

                # wait for a while...
                await asyncio.sleep(poll_delay)

    except asyncssh.misc.DisconnectError as ex:
        # error?
        context.host_set_message(host, colored(str(ex), 'red'))
        traceback.print_exc()

    finally:
        cprint(f"[{host:<{L}}] Bye!", color='yellow')


async def spawn_clients(hosts, verbose=False):
    # initial response
    for host in hosts:
        context.host_set_message(host, "Loading ...")

    name_length = max(len(host) for host in hosts)

    # launch all clients parallel
    await asyncio.gather(*[
        run_client(host, verbose=verbose, name_length=name_length) for host in hosts
    ])


# webserver handlers.
# monkey-patch ansi2html scheme. TODO: better color codes
import ansi2html
scheme = 'solarized'
ansi2html.style.SCHEME[scheme] = list(ansi2html.style.SCHEME[scheme])
ansi2html.style.SCHEME[scheme][0] = '#555555'
ansi_conv = ansi2html.Ansi2HTMLConverter(dark_bg=True, scheme=scheme)


async def handler(request):
    HEADER = '''
    <style>
        body { overflow-x: scroll; }
        nav.header { font-family: monospace; margin-bottom: 10px; }
        nav.header a, nav.header a:visited { color: #329af0; text-decoration: none; }
        nav.header a:hover { color: #a3daff; }

        /* no line break */
        pre.ansi2html-content { white-space: pre; word-wrap: normal; }
    </style>
    <nav class="header">
        gpustat-web by <a href="https://github.com/wookayin" target="_blank">@wookayin</a>
        <a href="javascript:clearTimeout(window.timer);" style="margin-left: 20px; color: #666666;"
            onclick="this.style.display='none';">[turn off auto-refresh]</a>
    </nav>'''

    FOOTER = '''
    <script>window.timer = setTimeout(function(){ window.location.reload(1); }, 5000);</script>
    '''

    body = ''
    for host, status in context.host_status.items():
        if not status:
            continue
        body += status

    body = HEADER + ansi_conv.convert(body) + FOOTER
    return web.Response(text=body, content_type='text/html')


def create_app(loop, hosts=['localhost'], verbose=True):
    app = web.Application()
    app.router.add_get('/', handler)

    async def start_background_tasks(app):
        app.loop.create_task(spawn_clients(hosts, verbose=verbose))
        await asyncio.sleep(0.1)
    app.on_startup.append(start_background_tasks)

    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hosts', nargs='*')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--port', type=int, default=48109)
    args = parser.parse_args()

    hosts = args.hosts or ['localhost']
    cprint(f"Hosts : {hosts}\n", color='green')

    loop = asyncio.get_event_loop()
    app = create_app(loop, hosts=hosts, verbose=args.verbose)

    try:
        # TODO: keyboardinterrupt handling
        web.run_app(app, host='0.0.0.0', port=args.port)
    finally:
        loop.close()


if __name__ == '__main__':
    main()
