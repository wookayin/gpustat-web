"""setup.py for gpustat-web."""

# flake8: noqa

from setuptools import setup
import sys


install_requires = [
    'six>=1.7',
    'termcolor',
    'ansi2html',
    'asyncssh>=1.16.0',
    'aiohttp>=3.6.3',  # GH-19
    'aiohttp_jinja2>=1.5',  # v1.5+ supports jinja2 v3.0
    'jinja2>=3.0.0',
    'aiohttp-devtools>=0.8',
    'packaging',
]

tests_requires = [
    'pytest',
]

def read_readme():
    with open('README.md', encoding='utf-8') as f:
        return f.read()


setup(
    name='gpustat-web',
    version='0.4.0.dev0',
    license='MIT',
    description='A web interface of gpustat --- consolidate status across multiple nodes.',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    url='https://github.com/wookayin/gpustat-web',
    author='Jongwook Choi',
    author_email='wookayin@gmail.com',
    keywords='nvidia-smi gpu cuda monitoring gpustat',
    classifiers=[
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Topic :: System :: Monitoring',
    ],
    packages=['gpustat_web'],
    entry_points={
        'console_scripts': ['gpustat-web=gpustat_web:main']
    },
    install_requires=install_requires,
    extras_require={'test': tests_requires},
    setup_requires=['pytest-runner'],
    tests_require=tests_requires,
    include_package_data=True,
    zip_safe=False,
    python_requires='>=3.6',
)
