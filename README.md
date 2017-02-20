# kubernetes

## Overview
This is kubernetes of fablib.

## Getting Started
```
# Setup test cluster
$ fab test:l=kubernetes,p='bootstrap|setup'

$ sudo virsh list --all
 Id    名前                         状態
 ----------------------------------------------------
 3     kubernetes-centos7-1           実行中
 4     kubernetes-centos7-2           実行中


# login master
$ ssh -A fabric@192.168.122.131

$ kubectl get nodes
NAME              STATUS    AGE
192.168.122.131   Ready     39m
192.168.122.132   Ready     35m
```

## Testing Guidelines
```
$ tox
```

## License
This is licensed under the MIT. See the [LICENSE](./LICENSE) file for details.
