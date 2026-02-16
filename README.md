gpustat-web
===========

A web interface of [`gpustat`][gpustat] ---
aggregate `gpustat` across multiple nodes.

<p align="center">
  <img src="https://github.com/wookayin/gpustat-web/raw/master/screenshot.png" width="800" height="192" />
</p>

**NOTE**: This project is in alpha stage. Errors and exceptions are not well handled, and it might use much network resources. Please use at your own risk!


Installation
-----

```
pip install gpustat-web
```

Python 3.6+ is required.

Usage
-----

Launch the application as follows. A SSH connection will be established to each of the specified hosts.
Make sure `ssh <host>` works under a proper authentication scheme such as SSH authentication.

```
# use current username on default port
gpustat-web --port 48109 HOST1 [... HOSTN]

# or specify user and port explicitly
gpustat-web --port 48109 [USER@]HOST1[:PORT] [... [USER@]HOSTN[:PORT]]
```

You might get "Host key is not trusted for `<host>`" errors. You'll have to accept and trust SSH keys of the host for the first time (it's stored in `~/.ssh/known_hosts`);
try `ssh <host>` in the command line, or `ssh -oStrictHostKeyChecking=accept-new <host>` to automatically accept the host key. You can also use an option `gpustat-web --no-verify-host` to bypass SSH Host key validation (although not recommended).

Note that asyncssh [does NOT obey](https://github.com/ronf/asyncssh/issues/108) the `~/.ssh/config` file
(e.g. alias, username, keyfile), so any config in `~/.ssh/config` might not be picked up.


[gpustat]: https://github.com/wookayin/gpustat/


### Endpoints

- `https://HOST:PORT/`: A webpage that updates automatically through websocket.
- `https://HOST:PORT/gpustat.html`: Result as a static HTML page.
- `https://HOST:PORT/gpustat.txt`: Result as a static plain text.
- `https://HOST:PORT/gpustat.ansi`: Result as a static text with ANSI color codes. Try `curl https://.../gpustat.ansi`

Query strings:

- `?nodes=gpu001,gpu002`: Select a subset of nodes to query and display


### Running as a HTTP (SSL/TLS) server

By default the web server will run as a HTTP server.
If you want to run a secure SSL/TLS server over the HTTPS protocol, use `--ssl-certfile` and `--ssl-keyfile` option.
You can use letsencrypt (`certbot`) to create a pair of SSL certificate and keyfile.

Troubleshoothing: Verify SSL/TLS handshaking (if TLS connections cannot be established)
```
openssl s_client -showcerts -connect YOUR_HOST.com:PORT < /dev/null
```


### More Examples

To see CPU usage as well:

```
python -m gpustat_web --exec 'gpustat --color --gpuname-width 25 && echo -en "CPU : \033[0;31m" && cpu-usage | ascii-bar 27'
```


License
-------

MIT License

Copyright (c) 2018-2023 Jongwook Choi
