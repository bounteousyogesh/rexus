###############################################################################
# Step 4: ALB — Application Load Balancer with path-based routing
#
# Looks up networking resources created in step 1 via data sources (tags).
# Run: cd 04-alb && terraform init && terraform plan && terraform apply
#
# Prerequisites: Step 1 (01-foundation) must be applied first.
# Routing rules:
#   /api/*   → backend target group (port 8000)
#   /health* → backend target group (port 8000)
#   default  → frontend target group (port 80)
###############################################################################

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

variable "backend_health_check_path" {
  type    = string
  default = "/health"
}

variable "frontend_health_check_path" {
  type    = string
  default = "/"
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── Data Sources: Look up foundation resources by tags ─────────────────────────

data "aws_vpc" "main" {
  tags = {
    Name        = "${local.name_prefix}-vpc"
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  tags = {
    Tier        = "public"
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_security_group" "alb" {
  tags = {
    Name        = "${local.name_prefix}-alb-sg"
    Project     = var.project
    Environment = var.environment
  }
}

# ── ALB ────────────────────────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [data.aws_security_group.alb.id]
  subnets            = data.aws_subnets.public.ids

  # Enable deletion protection for prod; off for dev
  enable_deletion_protection = false

  # Access logs (disabled for dev to avoid S3 bucket requirement)
  # enable_access_logs = false

  idle_timeout = 60

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb"
  })
}

# ── Target Groups ──────────────────────────────────────────────────────────────

# Backend: FastAPI on port 8000
resource "aws_lb_target_group" "backend" {
  name        = "${local.name_prefix}-backend-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.main.id
  target_type = "ip" # Required for Fargate

  health_check {
    enabled             = true
    path                = var.backend_health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-backend-tg"
    Component = "backend"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Frontend: nginx on port 80
resource "aws_lb_target_group" "frontend" {
  name        = "${local.name_prefix}-frontend-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.main.id
  target_type = "ip" # Required for Fargate

  health_check {
    enabled             = true
    path                = var.frontend_health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200,301,302"
  }

  deregistration_delay = 30

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-frontend-tg"
    Component = "frontend"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── HTTP Listener (port 80) ────────────────────────────────────────────────────
#
# Default action → frontend target group
# /api/* and /health* → backend target group (evaluated in priority order)

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # Default: serve frontend
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-http-listener"
  })
}

# Listener rule: /api/* → backend (priority 10)
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-api-rule"
  })
}

# Listener rule: /health → backend (priority 20)
resource "aws_lb_listener_rule" "health" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 20

  condition {
    path_pattern {
      values = ["/health", "/health/*"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-health-rule"
  })
}
