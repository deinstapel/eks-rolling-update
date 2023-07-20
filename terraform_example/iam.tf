data "aws_iam_policy_document" "eks_rolling_update" {
  statement {
    sid = "EKSRollingUpdate"
    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:TerminateInstanceInAutoScalingGroup",
      "autoscaling:SuspendProcesses",
      "autoscaling:ResumeProcesses",
      "autoscaling:UpdateAutoScalingGroup",
      "autoscaling:CreateOrUpdateTags",
      "autoscaling:DeleteTags",
      "ec2:DescribeLaunchTemplates",
      "ec2:DescribeInstances"
    ]
    resources = [
      "*"
    ]
  }
}

resource "aws_iam_policy" "eks_rolling_update" {
  name   = var.app_name
  path   = "/"
  policy = data.aws_iam_policy_document.eks_rolling_update.json
}

module "iam_assumable_role_eks_rolling_update" {
  source                        = "terraform-aws-modules/iam/aws//modules/iam-assumable-role-with-oidc"
  version                       = "4.24.1"
  create_role                   = true
  role_name                     = var.app_name
  provider_url                  = var.eks_oidc_provider
  role_policy_arns              = [aws_iam_policy.eks_rolling_update.arn]
  oidc_fully_qualified_subjects = ["system:serviceaccount:${var.namespace}:${var.app_name}"]
  tags = {
    "Name" = var.app_name
  }
}
