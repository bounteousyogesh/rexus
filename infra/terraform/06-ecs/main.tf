###############################################################################
# Step 6: ECS — Cluster, IAM Roles, Task Definitions, Services
#
# Looks up resources from steps 1–5 via data sources (tags/names).
# Run: cd 06-ecs && terraform init && terraform plan && terraform apply
#
# Prerequisites: Steps 1–5 must be applied and images pushed to ECR.
# Build & push images first:
#   ./infra/scripts/build-and-push.sh
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

variable "backend_image_tag" {
  description = "Docker image tag for the backend (e.g. latest, v1.0.0, git-sha)"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Docker image tag for the frontend"
  type        = string
  default     = "latest"
}

variable "backend_desired_count" {
  description = "Desired number of backend ECS tasks"
  type        = number
  default     = 1
}

variable "frontend_desired_count" {
  description = "Desired number of frontend ECS tasks"
  type        = number
  default     = 1
}

variable "llm_provider" {
  description = "LLM provider (bedrock or openai)"
  type        = string
  default     = "bedrock"
}

variable "llm_chat_model" {
  description = "LLM chat model identifier"
  type        = string
  default     = "anthropic.claude-opus-4-6-v1"
}

variable "llm_embed_model" {
  description = "LLM embedding model identifier"
  type        = string
  default     = "cohere.embed-v4:0"
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ── Data Sources: Networking (step 1) ─────────────────────────────────────────

data "aws_vpc" "main" {
  tags = {
    Name        = "${local.name_prefix}-vpc"
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  tags = {
    Tier        = "private"
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_security_group" "ecs" {
  tags = {
    Name        = "${local.name_prefix}-ecs-sg"
    Project     = var.project
    Environment = var.environment
  }
}

# ── Data Sources: ECR (step 3) ────────────────────────────────────────────────

data "aws_ecr_repository" "backend" {
  name = "${local.name_prefix}-backend"
}

data "aws_ecr_repository" "frontend" {
  name = "${local.name_prefix}-frontend"
}

# ── Data Sources: ALB Target Groups (step 4) ──────────────────────────────────

data "aws_lb_target_group" "backend" {
  name = "${local.name_prefix}-backend-tg"
}

data "aws_lb_target_group" "frontend" {
  name = "${local.name_prefix}-frontend-tg"
}

data "aws_lb" "main" {
  name = "${local.name_prefix}-alb"
}

# ── Data Sources: Secrets (step 2 + step 5) ───────────────────────────────────

data "aws_secretsmanager_secret" "db" {
  name = "${local.name_prefix}/db-password"
}

data "aws_secretsmanager_secret" "servicenow" {
  name = "${local.name_prefix}/servicenow"
}

data "aws_secretsmanager_secret" "app" {
  name = "${local.name_prefix}/app"
}

# ── Data Source: AWS Account ───────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cluster"
  })
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ── CloudWatch Log Groups ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}/backend"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-backend-logs"
    Component = "backend"
  })
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.name_prefix}/frontend"
  retention_in_days = 14

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-frontend-logs"
    Component = "frontend"
  })
}

# ── IAM: ECS Task Execution Role ──────────────────────────────────────────────
#
# Used by the ECS agent to pull images from ECR and retrieve secrets.

resource "aws_iam_role" "ecs_execution" {
  name = "${local.name_prefix}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-execution-role"
  })
}

# Attach the standard ECS execution policy (ECR pull, CloudWatch logs)
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read rexus/* secrets from Secrets Manager
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${local.name_prefix}-ecs-execution-secrets-policy"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadRexusSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${local.name_prefix}/*"
        ]
      },
      {
        Sid    = "DecryptSecrets"
        Effect = "Allow"
        Action = ["kms:Decrypt"]
        # Allow decryption with the default AWS-managed key
        Resource = ["arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alias/aws/secretsmanager"]
      }
    ]
  })
}

# ── IAM: ECS Task Role ────────────────────────────────────────────────────────
#
# Used by the application code inside the container.

resource "aws_iam_role" "ecs_task" {
  name = "${local.name_prefix}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-task-role"
  })
}

# Allow application to call Bedrock (LLM inference)
resource "aws_iam_role_policy" "ecs_task_bedrock" {
  name = "${local.name_prefix}-ecs-task-bedrock-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })
}

# Allow ECS Exec (for debugging — aws ecs execute-command)
resource "aws_iam_role_policy" "ecs_task_exec_command" {
  name = "${local.name_prefix}-ecs-task-exec-command-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSExec"
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# ── Task Definition: Backend ───────────────────────────────────────────────────

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = "${data.aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
          name          = "backend-http"
        }
      ]

      environment = [
        { name = "LLM_PROVIDER",    value = var.llm_provider },
        { name = "LLM_CHAT_MODEL",  value = var.llm_chat_model },
        { name = "LLM_EMBED_MODEL", value = var.llm_embed_model },
        { name = "AWS_REGION",      value = var.aws_region },
        { name = "REXUS_ENV",       value = "production" },
        { name = "CORS_ORIGINS",    value = "http://${data.aws_lb.main.dns_name}" },
        # Tell the app to read DATABASE_URL from the environment (set via secrets below)
        { name = "USE_ENV_DATABASE_URL", value = "true" }
      ]

      # Secrets are fetched from Secrets Manager at task launch time
      # and injected as environment variables. The "valueFrom" format:
      #   <secret-arn>:<json-key>::   extracts a specific key from a JSON secret.
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "${data.aws_secretsmanager_secret.db.arn}:url::"
        },
        {
          name      = "SERVICENOW_CLIENT_ID"
          valueFrom = "${data.aws_secretsmanager_secret.servicenow.arn}:SN_CLIENT_ID::"
        },
        {
          name      = "SERVICENOW_CLIENT_SECRET"
          valueFrom = "${data.aws_secretsmanager_secret.servicenow.arn}:SN_CLIENT_SECRET::"
        },
        {
          name      = "SERVICENOW_INSTANCE"
          valueFrom = "${data.aws_secretsmanager_secret.servicenow.arn}:SN_INSTANCE::"
        },
        {
          name      = "REXUS_JWT_SECRET"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:REXUS_JWT_SECRET::"
        },
        {
          name      = "REXUS_ADMIN_PASSWORD"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:REXUS_ADMIN_PASSWORD::"
        }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }

      # ECS Exec requires this
      linuxParameters = {
        initProcessEnabled = true
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-backend-task"
    Component = "backend"
  })

  depends_on = [
    aws_cloudwatch_log_group.backend,
    aws_iam_role_policy_attachment.ecs_execution_managed,
    aws_iam_role_policy.ecs_execution_secrets
  ]
}

# ── Task Definition: Frontend ──────────────────────────────────────────────────

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name_prefix}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = "${data.aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
          protocol      = "tcp"
          name          = "frontend-http"
        }
      ]

      environment = [
        # The ALB routes /api/* to the backend directly, so the frontend
        # uses the ALB DNS name as the backend URL for nginx proxying.
        { name = "BACKEND_URL", value = "http://${data.aws_lb.main.dns_name}" }
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "wget -qO- http://localhost:80/ || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "frontend"
        }
      }

      linuxParameters = {
        initProcessEnabled = true
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-frontend-task"
    Component = "frontend"
  })

  depends_on = [
    aws_cloudwatch_log_group.frontend,
    aws_iam_role_policy_attachment.ecs_execution_managed
  ]
}

# ── ECS Service: Backend ───────────────────────────────────────────────────────

resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  # ECS Exec for debugging (aws ecs execute-command)
  enable_execute_command = true

  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [data.aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = data.aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  # Allow rolling deployments without downtime
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Propagate tags to tasks for cost attribution
  propagate_tags = "SERVICE"

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-backend-service"
    Component = "backend"
  })

  # Ensure IAM roles are ready before the service is created
  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution_managed,
    aws_iam_role_policy.ecs_execution_secrets,
    aws_iam_role_policy.ecs_task_bedrock
  ]

  lifecycle {
    # Allow external tools (CI/CD) to update desired_count without Terraform drift
    ignore_changes = [desired_count]
  }
}

# ── ECS Service: Frontend ──────────────────────────────────────────────────────

resource "aws_ecs_service" "frontend" {
  name            = "${local.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [data.aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = data.aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  propagate_tags = "SERVICE"

  tags = merge(local.common_tags, {
    Name      = "${local.name_prefix}-frontend-service"
    Component = "frontend"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution_managed
  ]

  lifecycle {
    ignore_changes = [desired_count]
  }
}
