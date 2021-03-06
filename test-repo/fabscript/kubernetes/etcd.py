# coding: utf-8

from fabkit import task
from fablib.kubernetes import Etcd


@task
def setup():
    etcd = Etcd()
    etcd.setup()

    return {'status': 1}
