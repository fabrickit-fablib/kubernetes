# coding: utf-8

from fabkit import task
from fablib.kubernetes import Kubernetes


@task
def setup():
    kubernetes = Kubernetes()
    kubernetes.setup()

    return {'status': 1}
