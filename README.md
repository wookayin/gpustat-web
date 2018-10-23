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

Python 3.6+ is required.


[gpustat]: https://github.com/wookayin/gpustat/
