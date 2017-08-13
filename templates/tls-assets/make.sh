#!/bin/sh -xe

[ -e ca-key.pem ] || openssl genrsa -out ca-key.pem 4096
[ -e ca.pem ] || openssl req -x509 -new -nodes -key ca-key.pem -days 10000 -out ca.pem -subj "/CN=kube-ca"
[ -e kubernetes-key.pem ] || openssl genrsa -out kubernetes-key.pem 4096
[ -e kubernetes.csr ] || openssl req -new -key kubernetes-key.pem -out kubernetes.csr -subj "/CN=kubernetes" -config openssl.cnf
[ -e kubernetes.pem ] || openssl x509 -req -in kubernetes.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out kubernetes.pem -days 365 -extensions v3_req -extfile openssl.cnf
