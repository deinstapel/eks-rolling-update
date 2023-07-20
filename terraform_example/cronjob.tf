resource "kubernetes_cron_job_v1" "eks_rolling_update" {
  metadata {
    name      = local.app_name
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = local.app_name
    }
  }
  spec {
    concurrency_policy        = "Allow"
    failed_jobs_history_limit = 0
    schedule                  = var.schedule
    job_template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = local.app_name
        }
      }
      spec {
        active_deadline_seconds = 7200
        backoff_limit           = 5
        template {
          metadata {
            labels = {
              "app.kubernetes.io/name" = local.app_name
            }
          }
          spec {
            node_selector = {
              "kubernetes.io/arch" = "amd64"
            }
            service_account_name = local.pod_service_account_name
            container {
              image = "${var.update_image.image}:${var.update_image.tag}"
              name  = "eks-rolling-update"
              command = [
                "/usr/local/bin/eks_rolling_update.py",
                "-c",
                var.eks_cluster_name,
              ]
              env_from {
                config_map_ref {
                  name = kubernetes_config_map.pod_environment_vars.metadata.0.name
                }
              }
              resources {
                requests = {
                  cpu    = "100m"
                  memory = "128Mi"
                }
                limits = {
                  cpu    = "200m"
                  memory = "256Mi"
                }
              }
            }
          }
        }
      }
    }
  }
}
