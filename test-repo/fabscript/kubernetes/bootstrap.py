# coding: utf-8

from fabkit import task
from fablib.kubernetes import Bootstrap


@task
def setup():
    bootstrap = Bootstrap()
    bootstrap.setup()

    return {'status': 1}
