variable "app_name" {
  type        = string
  description = "The name of application"
  default     = "eks-rolling-update"
}

variable "namespace" {
  type        = string
  description = "The name of a pre-existing kubernetes namespace where eks-rolling-update will be deployed"
  default     = "kube-system"
}

variable "eks_oidc_provider" {
  type        = string
  description = "OIDC provider for the EKS cluster"
}

variable "cluster_autoscaler" {
  type = object({
    enabled    = bool
    namespace  = string
    deployment = string
    replicas   = number
  })
  description = "Configuration for cluster autoscaler"
  default = {
    enabled    = false
    namespace  = ""
    deployment = ""
    replicas   = 0
  }
}

variable "schedule" {
  type        = string
  description = "Schedule for running eks-rolling-update in cron format"
  default     = "0 3 * * *"
}

variable "eks_rolling_update_image" {
  type = object({
    image = string
    tag   = string
  })
  description = "Container image used for running the cronjob"
  default = {
    image = "ghcr.io/deinstapel/eks-rolling-update/eks-rolling-update"
    tag   = "edge"
  }
}
