from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException
import os
import subprocess
import json
import time
import sys
from .logger import logger
from eksrollup.config import app_config


def ensure_config_loaded():
    kube_config = os.getenv('KUBECONFIG', '~/.kube/config')
    kube_config = os.path.expanduser(kube_config)
    
    def load_kube_config_file(config_file, context):
        if os.path.isfile(config_file):
            logger.info(f"Loading kubeconfig from {config_file}")
            try:
                config.load_kube_config(config_file=config_file, context=context)
                logger.info(f"Kubernetes context {context} loaded successfully from {config_file}")
            except ConfigException as e:
                logger.warning(f"Could not configure kubernetes python client with the specified context {context} from {config_file}: {e}")
                raise Exception("Could not configure kubernetes python client with the specified context")
        else:
            logger.warning(f"Kubeconfig file {config_file} does not exist")
            raise Exception(f"Kubeconfig file {config_file} does not exist")

    # Try loading from the default kubeconfig file
    try:
        load_kube_config_file(kube_config, app_config['K8S_CONTEXT'])
    except Exception as e:
        logger.info(f"Failed to load context {app_config['K8S_CONTEXT']} from default kubeconfig, trying specific file")
        specific_kube_config = os.path.expanduser(f"~/.kube/{app_config['K8S_CONTEXT']}.yaml")
        try:
            load_kube_config_file(specific_kube_config, app_config['K8S_CONTEXT'])
        except Exception as e:
            logger.error(f"Failed to load context {app_config['K8S_CONTEXT']} from specific kubeconfig file {specific_kube_config}: {e}")
            raise Exception("Could not configure kubernetes python client with any kubeconfig file")

    proxy_url = os.getenv('HTTPS_PROXY', os.getenv('HTTP_PROXY', None))
    if proxy_url and not app_config['K8S_PROXY_BYPASS']:
        logger.info(f"Setting proxy: {proxy_url}")
        client.Configuration._default.proxy = proxy_url


def get_k8s_nodes(exclude_node_label_keys=app_config["EXCLUDE_NODE_LABEL_KEYS"]):
    """
    Returns a tuple of kubernetes nodes (nodes, excluded)
    """
    ensure_config_loaded()

    k8s_api = client.CoreV1Api()
    logger.info("Getting k8s nodes...")
    response = k8s_api.list_node()
    nodes = []
    excluded_nodes = []
    excluded_nodes_names = []
    if exclude_node_label_keys is not None:
        for node in response.items:
            if all(key not in node.metadata.labels for key in exclude_node_label_keys):
                nodes.append(node)
            else:
                excluded_nodes.append(node)
                excluded_nodes_names.append(node.metadata.name)
    else:
        nodes=response.items
    logger.info("Current total k8s node count is %d (included: %d, excluded: %d)", len(nodes)+len(excluded_nodes), len(nodes), len(excluded_nodes))
    logger.info("Excluded nodes: %s ", str(excluded_nodes_names))
    return nodes, excluded_nodes


def get_node_by_instance_id(k8s_nodes, instance_id, retries=3, delay=5):
    """
    Returns a K8S node name given an instance id. Expects the output of
    list_nodes as an input. Retries if the node is not found.
    """
    attempt = 0
    node_name = ""

    while attempt < retries:
        logger.info('Searching for k8s node name by instance id... Attempt {}'.format(attempt + 1))
        logger.info(f"Instance ID: {instance_id}")
        logger.info(f"K8s Nodes List Length: {len(k8s_nodes)}")

        # Print the structure of k8s_nodes for debugging
        # for index, k8s_node in enumerate(k8s_nodes):
        #     logger.info(f"Node {index} Type: {type(k8s_node)}")

        for k8s_node in k8s_nodes:
            if isinstance(k8s_node, dict):
                logger.error(f"Unexpected dict structure in k8s_nodes: {k8s_node}")
                continue
            if isinstance(k8s_node, list):
                logger.error(f"Unexpected list structure in k8s_nodes: {k8s_node}")
                continue
            try:
                # logger.info(f"Checking node: {k8s_node.metadata.name} with provider ID: {k8s_node.spec.provider_id}")
                if instance_id in k8s_node.spec.provider_id:
                    logger.info('InstanceId {} is node {} in kubernetes land'.format(instance_id, k8s_node.metadata.name))
                    node_name = k8s_node.metadata.name
                    break
            except AttributeError as e:
                logger.error(f"AttributeError: {e}")
                # logger.error(f"Node Data: {json.dumps(k8s_node.to_dict(), default=str)}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                # logger.error(f"Node Data: {json.dumps(k8s_node.to_dict(), default=str)}")

        if node_name:
            return node_name

        logger.warning(f"Could not find a k8s node name for instance id {instance_id} on attempt {attempt + 1}")
        logger.warning(f"Instance: {instance_id}, k8s_nodes: {[node.spec.provider_id for node in k8s_nodes]}")

        attempt += 1
        if attempt < retries:
            time.sleep(delay)
            k8s_nodes = get_k8s_nodes()  # Refresh the k8s_nodes list

    raise Exception(f"Could not find a k8s node name for instance id {instance_id} after {retries} attempts")


def is_autoscaler_running():
    k8s_api = client.AppsV1Api()
    try:
        response = k8s_api.read_namespaced_deployment(
            name=app_config['K8S_AUTOSCALER_DEPLOYMENT'],
            namespace=app_config['K8S_AUTOSCALER_NAMESPACE']
        )
        if response.status.replicas > 0:
            return True
        return False
    except ApiException as e:
        if e.status == 404:
            logger.info('K8s autoscaler deployment not found.')
            return False
        else:
            logger.error('Error checking autoscaler status: {}'.format(e))
            sys.exit(1)

def ensure_connection_to_cluster():
    try:
        v1 = client.CoreV1Api()
        logger.info("Listing namespaces in the cluster:")
        namespaces = v1.list_namespace(watch=False)
        for ns in namespaces.items:
            logger.info(f"Namespace: {ns.metadata.name}")
        logger.info("Connection to Kubernetes cluster is successful.")
    except Exception as e:
        logger.error(f"Failed to connect to Kubernetes cluster: {e}")
        raise Exception("Connection to Kubernetes cluster failed.")

def modify_k8s_autoscaler(action):
    """
    Pauses or resumes the Kubernetes autoscaler
    """

    ensure_config_loaded()

    # Option to uncomment this to validate connection to cluster by listing all namespaces in it
    # ensure_connection_to_cluster()

    if not is_autoscaler_running():
        logger.info('No k8s autoscaler running.')
        return

    # Configure API key authorization: BearerToken
    # create an instance of the API class
    k8s_api = client.AppsV1Api()
    if action == 'pause':
        logger.info('Pausing k8s autoscaler...')
        body = {'spec': {'replicas': 0}}
    elif action == 'resume':
        logger.info('Resuming k8s autoscaler...')
        body = {'spec': {'replicas': app_config['K8S_AUTOSCALER_REPLICAS']}}
    else:
        logger.info('Invalid k8s autoscaler option')
        sys.exit(1)
    try:
        k8s_api.patch_namespaced_deployment(
            app_config['K8S_AUTOSCALER_DEPLOYMENT'],
            app_config['K8S_AUTOSCALER_NAMESPACE'],
            body
        )
        logger.info('K8s autoscaler modified to replicas: {}'.format(body['spec']['replicas']))
    except ApiException as e:
        logger.info('Scaling of k8s autoscaler failed. Error code was {}, {}. Exiting.'.format(e.reason, e.body))
        sys.exit(1)


def delete_node(node_name):
    """
    Deletes a kubernetes node from the cluster
    """

    ensure_config_loaded()

    # create an instance of the API class
    k8s_api = client.CoreV1Api()
    logger.info("Deleting k8s node {}...".format(node_name))
    try:
        if not app_config['DRY_RUN']:
            k8s_api.delete_node(node_name)
        else:
            k8s_api.delete_node(node_name, dry_run="true")
        logger.info("Node deleted")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->delete_node: {}".format(e))


def cordon_node(node_name):
    """
    Cordon a kubernetes node to avoid new pods being scheduled on it
    """

    ensure_config_loaded()

    # create an instance of the API class
    k8s_api = client.CoreV1Api()
    logger.info("Cordoning k8s node {}...".format(node_name))
    try:
        api_call_body = client.V1Node(spec=client.V1NodeSpec(unschedulable=True))
        if not app_config['DRY_RUN']:
            k8s_api.patch_node(node_name, api_call_body)
        else:
            k8s_api.patch_node(node_name, api_call_body, dry_run=True)
        logger.info("Node cordoned")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->patch_node: {}".format(e))


def taint_node(node_name):
    """
    Taint a kubernetes node to avoid new pods being scheduled on it
    """

    ensure_config_loaded()

    k8s_api = client.CoreV1Api()
    logger.info("Adding taint to k8s node {}...".format(node_name))
    try:
        taint = client.V1Taint(effect='NoSchedule', key='eks-rolling-update')
        api_call_body = client.V1Node(spec=client.V1NodeSpec(taints=[taint]))
        if not app_config['DRY_RUN']:
            k8s_api.patch_node(node_name, api_call_body)
        else:
            k8s_api.patch_node(node_name, api_call_body, dry_run=True)
        logger.info("Added taint to the node")
    except ApiException as e:
        logger.info("Exception when calling CoreV1Api->patch_node: {}".format(e))


def drain_node(node_name):
    """
    Drains the specified node using the Kubernetes API.
    """
    # Ensure the Kubernetes configuration is loaded
    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()

    v1 = client.CoreV1Api()

    # Evict pods from the node
    try:
        logger.info(f"Draining node {node_name}...")
        pods = v1.list_pod_for_all_namespaces(watch=False, field_selector=f"spec.nodeName={node_name}")
        for pod in pods.items:
            if pod.metadata.owner_references and any(owner.kind == "DaemonSet" for owner in pod.metadata.owner_references):
                logger.info(f"Skipping DaemonSet pod {pod.metadata.name} in namespace {pod.metadata.namespace}")
                continue
            eviction = client.V1beta1Eviction(
                metadata=client.V1ObjectMeta(name=pod.metadata.name, namespace=pod.metadata.namespace),
                delete_options=client.V1DeleteOptions(grace_period_seconds=0)
            )
            try:
                v1.create_namespaced_pod_eviction(name=pod.metadata.name, namespace=pod.metadata.namespace, body=eviction)
                logger.info(f"Evicted pod {pod.metadata.name} from namespace {pod.metadata.namespace}")
            except ApiException as e:
                logger.error(f"Failed to evict pod {pod.metadata.name} from namespace {pod.metadata.namespace}: {e}")
                raise Exception(f"Failed to evict pod {pod.metadata.name} from namespace {pod.metadata.namespace}: {e}")

    except ApiException as e:
        logger.error(f"Failed to drain node {node_name}: {e}")
        raise Exception(f"Failed to drain node {node_name}")




def k8s_nodes_ready(max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that all nodes in a cluster are Ready
    """
    logger.info('Checking k8s nodes health status...')
    retry_count = 1
    healthy_nodes = False
    while retry_count < max_retry:
        # reset healthy nodes after every loop
        healthy_nodes = True
        retry_count += 1
        nodes, excluded_nodes = get_k8s_nodes()
        for node in nodes:
            conditions = node.status.conditions
            for condition in conditions:
                if condition.type == "Ready" and condition.status == "False":
                    logger.info("Node {} is not healthy - Ready: {}".format(
                        node.metadata.name,
                        condition.status)
                    )
                    healthy_nodes = False
                elif condition.type == "Ready" and condition.status == "True":
                    # condition status is a string
                    logger.info("Node {}: Ready".format(node.metadata.name))
        if healthy_nodes:
            logger.info('All k8s nodes are healthy')
            break
        logger.info('Retrying node health...')
        time.sleep(wait)
    return healthy_nodes


def k8s_nodes_count(desired_node_count, max_retry=app_config['GLOBAL_MAX_RETRY'], wait=app_config['GLOBAL_HEALTH_WAIT']):
    """
    Checks that the number of nodes in k8s cluster matches given desired_node_count
    """
    logger.info('Checking k8s expected nodes are online after asg scaled up...')
    retry_count = 1
    nodes_online = False
    while retry_count < max_retry:
        nodes_online = True
        retry_count += 1
        nodes, excluded_nodes = get_k8s_nodes()
        logger.info('Current k8s node count is {}'.format(len(nodes)))
        if len(nodes) < desired_node_count:
            nodes_online = False
            logger.info('Waiting for k8s nodes to reach count {}...'.format(desired_node_count))
            time.sleep(wait)
        else:
            logger.info('Reached desired k8s node count of {}'.format(len(nodes)))
            break
    return nodes_online
