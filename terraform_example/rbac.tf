resource "kubernetes_service_account" "eks_rolling_update" {
  metadata {
    name      = local.pod_service_account_name
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = module.iam_assumable_role_eks_rolling_update.iam_role_arn
    }
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }
}

resource "kubernetes_role" "cluster_autoscaler_scale" {
  count = var.cluster_autoscaler.enabled ? 1 : 0
  metadata {
    name      = "update-cluster-autoscaler"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }
  rule {
    verbs          = ["patch"]
    api_groups     = ["apps"]
    resources      = ["deployments"]
    resource_names = [var.cluster_autoscaler.deployment]
  }
}

resource "kubernetes_role_binding" "cluster_autoscaler_scale" {
  count = var.cluster_autoscaler.enabled ? 1 : 0
  metadata {
    name      = "update-cluster-autoscaler"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }
  subject {
    kind      = "ServiceAccount"
    name      = local.pod_service_account_name
    namespace = var.namespace
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = "update-cluster-autoscaler"
  }
}

resource "kubernetes_cluster_role" "system_node_drainer" {
  metadata {
    name = "update-node-drainer"
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }
  rule {
    verbs      = ["create"]
    api_groups = [""]
    resources  = ["pods/eviction"]
  }
  rule {
    verbs      = ["get", "list"]
    api_groups = [""]
    resources  = ["pods"]
  }
  rule {
    verbs      = ["get", "patch", "list", "watch"]
    api_groups = [""]
    resources  = ["nodes"]
  }
  rule {
    verbs      = ["get", "list"]
    api_groups = ["apps"]
    resources  = ["statefulsets", "daemonsets", "deployments", "replicasets"]
  }
}

resource "kubernetes_cluster_role_binding" "node_drainer_clusterrole_bind" {
  metadata {
    name = "update-node-drainer"
    labels = {
      "app.kubernetes.io/name" = var.app_name
    }
  }
  subject {
    kind      = "ServiceAccount"
    name      = local.pod_service_account_name
    namespace = var.namespace
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "update-node-drainer"
  }
}
