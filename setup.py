#!/usr/bin/env python
#:coding=utf-8:

from setuptools import setup, find_packages
 
setup (
    name='kombu-appengine-pullqueue',
    version='0.1',
    description='A kombu backend for the appengine pull hueue API',
    author='Ian Lewis',
    author_email='ianmlewis@gmail.com',
    url='https://github.com/IanLewis/kombu-appengine-pullqueue',
    classifiers=[
      'Development Status :: 3 - Alpha',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: BSD License',
      'Programming Language :: Python',
      'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    packages=find_packages(),
    install_requires=[
        'kombu>=2.5,<2.6',
        'google-api-python-client>=1.2,<1.3',
    ],
)
