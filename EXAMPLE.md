# Example

## Test network of docker
```
# node1
$ sudo docker run -it --name centos centos:centos7.1.1503 /bin/bash
[sudo] password for fabric:
Unable to find image 'centos:centos7.1.1503' locally
Trying to pull repository docker.io/library/centos ...
centos7.1.1503: Pulling from docker.io/library/centos
f6e4e6bc8376: Pull complete
Digest: sha256:c65fadf49b5e7185a504029d88fc892cbcf41d868fb7059a84db05fb37fe6603
Status: Downloaded newer image for docker.io/centos:centos7.1.1503
[root@739fbc9e27f1 /]# ip a
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host
       valid_lft forever preferred_lft forever
5: eth0@if6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UP
    link/ether 02:42:0a:14:0f:02 brd ff:ff:ff:ff:ff:ff
    inet 10.20.15.2/24 scope global eth0
       valid_lft forever preferred_lft forever
    inet6 fe80::42:aff:fe14:f02/64 scope link
       valid_lft forever preferred_lft forever

# node2
$ sudo docker run -it --name centos centos:centos7.1.1503 /bin/bash
[root@b76f44a45148 /]# ip a
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host
       valid_lft forever preferred_lft forever
5: eth0@if6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc noqueue state UP
    link/ether 02:42:0a:14:2f:02 brd ff:ff:ff:ff:ff:ff
    inet 10.20.47.2/24 scope global eth0
       valid_lft forever preferred_lft forever
    inet6 fe80::42:aff:fe14:2f02/64 scope link
       valid_lft forever preferred_lft forever
[root@b76f44a45148 /]# ping 10.20.15.2
PING 10.20.15.2 (10.20.15.2) 56(84) bytes of data.
64 bytes from 10.20.15.2: icmp_seq=1 ttl=62 time=1.58 ms
64 bytes from 10.20.15.2: icmp_seq=2 ttl=62 time=0.216 ms
64 bytes from 10.20.15.2: icmp_seq=3 ttl=62 time=0.309 ms
```

## set config of kubectl
```
$ kubectl config set-credentials myself --username=admin --password=admin \
kubectl config set-cluster local-server --server=http://localhost:8080 \
kubectl config set-context default-context --cluster=local-server --user=myself \
kubectl config use-context default-context \
kubectl config set contexts.default-context.namespace default \
```

## Helloworld of pod, replicationcontroller, service
```
$ vim httpd.yaml
apiVersion: v1
kind: Pod
metadata:
  name: httpd
    labels:
      app: httpd
      spec:
        containers:
        - name: httpd
          image: httpd
          ports:
          - containerPort: 80

$ kubectl create -f httpd.yaml

$ kubectl get pods
NAME                  READY     STATUS             RESTARTS   AGE
httpd                 1/1       Running            0          29m

$ kubectl get pod httpd -o yaml
...
  hostIP: 192.168.122.51
  phase: Running
  podIP: 10.20.47.3

$ curl 10.20.47.3
<html><body><h1>It works!</h1></body></html>

$ vim httpd-rc.yaml
apiVersion: v1
kind: ReplicationController
metadata:
  name: httpd-rc
spec:
  replicas: 2
  template:
    metadata:
      labels:
        app: httpd
        tier: frontend
    spec:
      containers:
      - name: httpd
        image: httpd
        ports:
        - containerPort: 80

$ kubectl create -f httpd-rc.yaml
$ kubectl get replicationcontroller
NAME       DESIRED   CURRENT   AGE
httpd-rc   2         2         5m

$ kubectl get pod
NAME             READY     STATUS    RESTARTS   AGE
httpd-rc-39ue0   1/1       Running   0          6m
httpd-rc-fj3nh   1/1       Running   0          6m


$ vim httpd-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: httpd-service
spec:
  type: NodePort
  ports:
  - port: 80
    nodePort: 30080
  selector:
    app: httpd
    tier: frontend

$ kubectl get service
NAME            CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
httpd-service   10.254.121.16   nodes         80/TCP    1m

$ curl 192.168.122.51:30080
<html><body><h1>It works!</h1></body></html>
```
