###############################################################################
# Step 5: Secrets — Secrets Manager secrets for application credentials
#
# Run: cd 05-secrets && terraform init && terraform plan && terraform apply
#
# No dependencies on other steps.
# After apply, populate real values:
#   aws secretsmanager put-secret-value \
#     --secret-id rexus/dev/servicenow \
#     --secret-string '{"SN_CLIENT_ID":"real","SN_CLIENT_SECRET":"real","SN_INSTANCE":"real"}'
###############################################################################

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "rexus"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "admin_password" {
  description = "Admin password for the application (leave empty to auto-generate)"
  type        = string
  sensitive   = true
  default     = ""
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── Auto-generated secrets ─────────────────────────────────────────────────────

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

resource "random_password" "admin_password" {
  # Only generated if var.admin_password is empty
  count   = var.admin_password == "" ? 1 : 0
  length  = 24
  special = true
  # Avoid characters that break shell quoting
  override_special = "!#%^*-_=+"
}

locals {
  effective_admin_password = var.admin_password != "" ? var.admin_password : random_password.admin_password[0].result
}

# ── Secret: ServiceNow credentials ────────────────────────────────────────────
#
# Placeholder values — update with real ServiceNow OAuth credentials after apply:
#   aws secretsmanager put-secret-value \
#     --secret-id rexus/dev/servicenow \
#     --secret-string '{"SN_CLIENT_ID":"...","SN_CLIENT_SECRET":"...","SN_INSTANCE":"..."}'

resource "aws_secretsmanager_secret" "servicenow" {
  name                    = "${local.name_prefix}/servicenow"
  description             = "ServiceNow OAuth credentials for ${local.name_prefix}"
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-servicenow-secret"
    Component = "servicenow"
  })
}

resource "aws_secretsmanager_secret_version" "servicenow" {
  secret_id = aws_secretsmanager_secret.servicenow.id
  secret_string = jsonencode({
    SN_CLIENT_ID     = "PLACEHOLDER_REPLACE_ME"
    SN_CLIENT_SECRET = "PLACEHOLDER_REPLACE_ME"
    SN_INSTANCE      = "PLACEHOLDER_REPLACE_ME"
  })

  # Prevent Terraform from overwriting real values on subsequent applies.
  # After first apply, update the secret manually and ignore changes here.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ── Secret: Application secrets ───────────────────────────────────────────────

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name_prefix}/app"
  description             = "Application secrets (JWT, admin credentials) for ${local.name_prefix}"
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-app-secret"
    Component = "app"
  })
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    REXUS_JWT_SECRET      = random_password.jwt_secret.result
    REXUS_ADMIN_PASSWORD  = local.effective_admin_password
  })
}
