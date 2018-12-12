gpustat-web
===========

A web interface of [`gpustat`][gpustat] --- consolidate across your cluster.


Usage
-----

Launch the application as follows. SSH connections will be established to each of the specified hosts.
Make sure ssh works under a proper authentication scheme such as publickey.

```
python -m gpustat_web --port 48109 HOST1 [... HOSTN]
```

### More Examples

To see CPU usage as well:

```
python -m gpustat_web --exec 'gpustat --color --gpuname-width 25; echo -en "CPU : \033[0;31m"; cpu-usage | ascii-bar 27'
```


Python 3.6+ is required.


[gpustat]: https://github.com/wookayin/gpustat/
