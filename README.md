# kubernetes

## Overview
This is kubernetes of fablib.

## Getting Started
```
# Setup test cluster
$ fab test:l=kubernetes

$ sudo virsh list --all
 Id    名前                         状態
 ----------------------------------------------------
  12    centos7                        実行中
  13    centos7_2                      実行中

# login master
$ ssh -A fabric@192.168.122.50

$ kubectl get nodes
NAME             STATUS    AGE
192.168.122.50   Ready     2h
192.168.122.51   Ready     2h
```

## Testing Guidelines
```
$ tox
```

## License
This is licensed under the MIT. See the [LICENSE](./LICENSE) file for details.


## Reference
* [Kubernetes クラスタの外からのアクセスに ClusterIP をロードバランサとして使う] (http://qiita.com/albatross/items/25fe2a0e9f21f08e974a)
