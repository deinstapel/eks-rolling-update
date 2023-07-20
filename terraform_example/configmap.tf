resource "kubernetes_config_map" "pod_environment_vars" {
  metadata {
    name      = var.app_name
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }

  data = merge({
    EXTRA_DRAIN_ARGS     = "--timeout=300s"
    GLOBAL_HEALTH_WAIT   = "30"
    GLOBAL_MAX_RETRY     = "100"
    BETWEEN_NODES_WAIT   = "10"
    CLUSTER_HEALTH_WAIT  = "120"
    CLUSTER_HEALTH_RETRY = "20"
    }, (var.cluster_autoscaler.enabled ? {
      K8S_AUTOSCALER_ENABLED    = "True"
      K8S_AUTOSCALER_NAMESPACE  = var.cluster_autoscaler.namespace
      K8S_AUTOSCALER_DEPLOYMENT = var.cluster_autoscaler.deployment
      K8S_AUTOSCALER_REPLICAS   = var.cluster_autoscaler.replicas
  } : {}))
}
