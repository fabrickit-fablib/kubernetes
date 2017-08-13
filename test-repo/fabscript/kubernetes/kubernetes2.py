# coding: utf-8

from fabkit import task
from fablib.kubernetes import Kubernetes


@task
def setup():
    kubernetes = Kubernetes()
    kubernetes.approve_certificate()

    return {'status': 1}
