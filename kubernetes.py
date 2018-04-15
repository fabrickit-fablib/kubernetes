# coding: utf-8

import time
from fabkit import *  # noqa
from fablib.base import SimpleBase


class Kubernetes(SimpleBase):
    def __init__(self):
        self.data_key = 'kubernetes'
        self.data = {
            'service_cluster_ip_range': '10.32.0.0/16',
            'cluster_dns': '10.32.0.10',
            'dns_domain': 'cluster.local',
            'cluster_cidr': '10.200.0.0/16',
            'version': '1.10.1',  # 1.7.3
            'network_plugin': 'cni',
            'helm': {
                'version': '2.6.1',
            },
            'tiller': {
                'version': '2.6.1',
            },
            'addons': ['roles', 'calico', 'kube-dns', 'tiller-deploy']
        }

        self.packages = {}

        self.services = {
            'CentOS .*': [
                'kubelet',
            ]
        }

    def init_after(self):

        self.data.update({
            'bootstrap_token': databag.get('kubernetes.bootstrap_token'),
            'etcd_servers': databag.get('kubernetes.etcd_servers'),
            'certificate_aythority_data': databag.get('kubernetes.certificate_aythority_data'),
            'api_servers': databag.get('kubernetes.api_servers'),

            # 'hostname': env.host,
            # 'my_ip': env.node['ip']['default_dev']['ip'],
            # 'ssl_certs_host_path': '/usr/share/pki/ca-trust-source/anchors',  # if coreos path: /usr/share/ca-certificates  # noqa
            # 'addons': ['kube-proxy', 'kube-dns', 'kubernetes-dashboard',
            #            'heapster', 'monitoring-grafana', 'monitoring-influxdb',
            #            'logging-es', 'logging-kibana', 'fluentd-es', 'tiller-deploy',
            #            'prometheus', 'prometheus-node-exporter']
        })

        splited_version = self.data['version'].split('.')
        if int(splited_version[1]) >= 10:
            self.data['kube_apiserver_options'] = '--enable-bootstrap-token-auth --authorization-mode=Node,RBAC' \
                + ' --kubelet-client-certificate=/var/lib/kubernetes/kubernetes.pem' \
                + ' --kubelet-client-key=/var/lib/kubernetes/kubernetes-key.pem'
            self.data['kubelet_options'] = '--bootstrap-kubeconfig=/var/lib/kubelet/bootstrap.kubeconfig' \
                + ' --anonymous-auth=false' \
                + ' --client-ca-file=/root/kubernetes-tls-assets/ca.pem'
        else:
            self.data['kube_apiserver_options'] = '--experimental-bootstrap-token-auth --authorization-mode=RBAC'
            self.data['kubelet_options'] = '--api-servers={0} '.format(databag.get('kubernetes.api_servers')) \
                + '--experimental-bootstrap-kubeconfig=/var/lib/kubelet/bootstrap.kubeconfig'

    def setup(self):
        data = self.init()
        filer.mkdir('/var/lib/kubernetes/')
        filer.mkdir('/var/run/kubernetes/')
        filer.mkdir('/var/lib/kubelet/')
        filer.mkdir('/var/lib/kube-proxy/')
        filer.mkdir('/etc/kubernetes/')
        filer.mkdir('/etc/kubernetes/addons')

        with api.cd('/tmp'):
            for binary in ['kubectl', 'kube-apiserver', 'kube-controller-manager', 'kube-scheduler', 'kube-proxy', 'kubelet']:
                if not filer.exists('/usr/bin/{0}'.format(binary)):
                    run('wget https://storage.googleapis.com/kubernetes-release/release/v{0}/bin/linux/amd64/{1}'.format(data['version'], binary))
                    sudo('chmod 755 {0}'.format(binary))
                    sudo('cp {0} /usr/bin/'.format(binary))

            if not filer.exists('/usr/bin/docker'):
                run('wget https://get.docker.com/builds/Linux/x86_64/docker-1.12.6.tgz')
                run('tar -xvf docker-1.12.6.tgz')
                sudo('mv docker/docker* /usr/bin/')

            if not filer.exists('/opt/cni'):
                filer.mkdir('/opt/cni')
                run('wget https://storage.googleapis.com/kubernetes-release/network-plugins/cni-amd64-0799f5732f2a11b329d9e3d51b9c8f2e3759f2ff.tar.gz')
                sudo('tar -xvf cni-amd64-0799f5732f2a11b329d9e3d51b9c8f2e3759f2ff.tar.gz -C /opt/cni')

        filer.template('/var/lib/kubernetes/token.csv', data=data)
        sudo('cp /root/kubernetes-tls-assets/{ca,kubernetes,kubernetes-key}.pem /var/lib/kubernetes/')

        filer.template('/etc/kubernetes/static-password.csv', data=data)

        filer.template('/etc/systemd/system/kube-apiserver.service', data=data)
        filer.template('/etc/systemd/system/kube-controller-manager.service', data=data)
        filer.template('/etc/systemd/system/kube-scheduler.service', data=data)
        filer.template('/etc/systemd/system/kubelet.service', data=data)
        filer.template('/etc/systemd/system/kube-proxy.service', data=data)
        filer.template('/etc/systemd/system/docker.service', data=data)
        sudo('systemctl daemon-reload')
        sudo('systemctl start docker')

        if env.host == env.hosts[0]:
            sudo('systemctl start kube-apiserver')
            sudo('systemctl start kube-controller-manager')
            sudo('systemctl start kube-scheduler')
            sudo('cp /root/kubernetes-tls-assets/ca-key.pem /var/lib/kubernetes/')

            if not filer.exists('/root/kubeconfigs'):
                filer.mkdir('/root/kubeconfigs')

                sudo('kubectl config set-cluster kubernetes-the-hard-way'
                     ' --certificate-authority=/var/lib/kubernetes/ca.pem'
                     ' --embed-certs=true'
                     ' --server=https://{0}:6443'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig'.format(data['vip']))

                sudo('kubectl config set-credentials kubelet-bootstrap'
                     ' --token={0}'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig'.format(data['bootstrap_token']))

                sudo('kubectl config set-context default'
                     ' --cluster=kubernetes-the-hard-way'
                     ' --user=kubelet-bootstrap'
                     ' --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig')

                sudo('kubectl config use-context default --kubeconfig=/root/kubeconfigs/bootstrap.kubeconfig')

                sudo('kubectl config set-cluster kubernetes-the-hard-way'
                     ' --certificate-authority=/var/lib/kubernetes/ca.pem'
                     ' --embed-certs=true'
                     ' --server=https://{0}:6443'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig'.format(data['vip']))

                sudo('kubectl config set-credentials kube-proxy'
                     ' --client-certificate=/root/kubernetes-tls-assets/kube-proxy.pem'
                     ' --client-key=/root/kubernetes-tls-assets/kube-proxy-key.pem'
                     ' --embed-certs=true'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                sudo('kubectl config set-context default'
                     ' --cluster=kubernetes-the-hard-way'
                     ' --user=kube-proxy'
                     ' --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                sudo('kubectl config use-context default --kubeconfig=/root/kubeconfigs/kube-proxy.kubeconfig')

                bootstrap_kubeconfig = sudo('cat /root/kubeconfigs/bootstrap.kubeconfig')
                databag.set('kubernetes.bootstrap_kubeconfig', str(bootstrap_kubeconfig))
                kube_proxy_kubeconfig = sudo('cat /root/kubeconfigs/kube-proxy.kubeconfig')
                databag.set('kubernetes.kube_proxy_kubeconfig', str(kube_proxy_kubeconfig))
                with api.warn_only():
                    while True:
                        result = run('ss -ln | grep ":6443 "')
                        if result.return_code == 0:
                            break
                        time.sleep(10)

                run('kubectl create clusterrolebinding kubelet-cluster-admin-binding --clusterrole=cluster-admin --user=kubelet-bootstrap')

                # run('kubectl create clusterrolebinding kubelet-bootstrap --clusterrole=system:node-bootstrapper --user=kubelet-bootstrap')

        bootstrap_kubeconfig = databag.get('kubernetes.bootstrap_kubeconfig')
        kube_proxy_kubeconfig = databag.get('kubernetes.kube_proxy_kubeconfig')
        filer.file('/var/lib/kubelet/bootstrap.kubeconfig', src_str=bootstrap_kubeconfig)
        filer.file('/var/lib/kube-proxy/kube-proxy.kubeconfig', src_str=kube_proxy_kubeconfig)
        sudo('systemctl start kubelet')
        sudo('systemctl start kube-proxy')

    def approve_certificate(self):
        data = self.init()
        run("for csr in `kubectl get csr | grep Pending | awk '{print $1}'`; do kubectl certificate approve $csr; done")

        sudo('kubectl get secret calico-etcd-secrets -n kube-system'
             ' || kubectl create secret generic calico-etcd-secrets -n kube-system'
             ' --from-file=etcd-key=/etc/etcd/kubernetes-key.pem'
             ' --from-file=etcd-cert=/etc/etcd/kubernetes.pem'
             ' --from-file=etcd-ca=/etc/etcd/ca.pem')

        filer.mkdir('/var/log/calico')
        filer.mkdir('/etc/calico')
        filer.template('/etc/calico/calicoctl.cfg', data=data)
        if not filer.exists('/usr/bin/calicoctl'):
            run('wget https://github.com/projectcalico/calicoctl/releases/download/v1.4.1/calicoctl')
            run('chmod 755 calicoctl')
            sudo('sudo mv calicoctl /usr/bin/')

        if not filer.exists('/usr/bin/helm'):
            run('wget https://storage.googleapis.com/kubernetes-helm/helm-v{0}-linux-amd64.tar.gz'.format(
                data['helm']['version']
            ))
            run('tar -xf helm-v{0}-linux-amd64.tar.gz'.format(
                data['helm']['version']
            ))
            sudo('mv linux-amd64/helm /usr/bin/')

        for addon in data['addons']:
            addon_file = '/etc/kubernetes/addons/{0}.yaml'.format(addon)
            filer.template(addon_file, data=data)
            sudo('kubectl apply -f {0}'.format(addon_file))
