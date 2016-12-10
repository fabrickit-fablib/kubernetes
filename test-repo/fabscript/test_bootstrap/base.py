# cording: utf-8

from fabkit import task, container, env


@task
def setup():
    container.delete(env.cluster['container1'])
    container.create(env.cluster['container1'])
