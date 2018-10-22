"""
gpustat.web

@author Jongwook Choi
"""

import asyncio
import asyncssh
import sys

from datetime import datetime
from copy import deepcopy
from collections import OrderedDict

from termcolor import cprint
from aiohttp import web as web


# the global context object
class Context(object):
    def __init__(self):
        self.host_status = OrderedDict()

context = Context()


# async handlers to collect gpu stats
async def run_client(host, poll_delay=5.0, verbose=False):
    async with asyncssh.connect(host) as conn:
        print(f"[{host}] connection established!")

        while True:
            if False: #verbose: XXX DEBUG
                print(f"[{host}] querying... ")

            try:
                result = await conn.run('gpustat --color')
            except GeneratorExit:
                # interrupted
                break

            now = datetime.now().strftime('%Y/%m/%d-%H:%M:%S.%f')
            if result.exit_status != 0:
                cprint(f"[{now} [{host}] error, exitcode={result.exit_status}", color='red')
            else:
                if verbose:
                    cprint(f"[{now} [{host}] OK from gpustat ({len(result.stdout)} bytes)", color='cyan')
                # update data
                context.host_status[host] = result.stdout

            # wait for a while...
            await asyncio.sleep(poll_delay)

    print(f"[{host}] Bye!", color='yellow')


async def spawn_clients(hosts, verbose=False):
    # launch all clients parallel
    await asyncio.gather(*[
        run_client(host, verbose=verbose) for host in hosts
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
        nav.header { font-family: monospace; margin-bottom: 10px; }
        nav.header a, nav.header a:visited { color: #329af0; }
        nav.header a:hover { color: #a3daff; }
    </style>
    <nav class="header">
        gpustat-web by <a href="https://github.com/wookayin" target="_blank">@wookayin</a>
    </nav>'''

    FOOTER = '''
    <script>timer = setTimeout(function(){ window.location.reload(1); }, 5000);</script>
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
