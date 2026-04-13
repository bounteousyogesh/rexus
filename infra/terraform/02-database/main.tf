###############################################################################
# Step 2: Database — RDS PostgreSQL 16 with pgvector
#
# Looks up networking resources created in step 1 via data sources (tags).
# Run: cd 02-database && terraform init && terraform plan && terraform apply
#
# Prerequisites: Step 1 (01-foundation) must be applied first.
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

variable "db_name" {
  type    = string
  default = "rexus"
}

variable "db_username" {
  type    = string
  default = "rexus"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 50
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

data "aws_security_group" "rds" {
  tags = {
    Name        = "${local.name_prefix}-rds-sg"
    Project     = var.project
    Environment = var.environment
  }
}

# ── Random password ────────────────────────────────────────────────────────────

resource "random_password" "db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# ── Secrets Manager: Store DB password ────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.name_prefix}/db-password"
  description             = "RDS PostgreSQL master password for ${local.name_prefix}"
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-password"
  })
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_password.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    dbname   = var.db_name
    host     = aws_db_instance.main.address
    port     = 5432
    # Full DATABASE_URL for the application
    url = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_db_instance.main.address}:5432/${var.db_name}"
  })
  # Ensure RDS is created first so we can include the host
  depends_on = [aws_db_instance.main]
}

# ── DB Subnet Group ────────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name        = "${local.name_prefix}-db-subnet-group"
  description = "DB subnet group for ${local.name_prefix} RDS"
  subnet_ids  = data.aws_subnets.private.ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-subnet-group"
  })
}

# ── Parameter Group: Enable pgvector and pg_trgm ──────────────────────────────
#
# PostgreSQL 16 on RDS supports pgvector natively via shared_preload_libraries.
# pg_trgm is included in RDS by default but we pin it explicitly.

resource "aws_db_parameter_group" "main" {
  name        = "${local.name_prefix}-pg16"
  family      = "postgres16"
  description = "PostgreSQL 16 parameters for ${local.name_prefix} — enables pgvector"

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements,pgvector"
    apply_method = "pending-reboot"
  }

  # Allow vector index builds to use more memory
  parameter {
    name         = "maintenance_work_mem"
    value        = "262144" # 256 MB in KB
    apply_method = "immediate"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-pg16-params"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ── RDS Instance ───────────────────────────────────────────────────────────────

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-postgres"

  # Engine
  engine               = "postgres"
  engine_version       = "16.6"
  instance_class       = var.db_instance_class
  parameter_group_name = aws_db_parameter_group.main.name

  # Storage
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 200 # Allow autoscaling up to 200 GB
  storage_type          = "gp3"
  storage_encrypted     = true

  # Database
  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [data.aws_security_group.rds.id]
  publicly_accessible    = false
  port                   = 5432

  # Availability — single-AZ for dev (set multi_az=true for prod)
  multi_az = false

  # Backup
  backup_retention_period   = 7
  backup_window             = "03:00-04:00"
  maintenance_window        = "mon:04:00-mon:05:00"
  delete_automated_backups  = true

  # Protection
  deletion_protection       = false # Set true for prod
  skip_final_snapshot       = true  # Set false for prod
  final_snapshot_identifier = "${local.name_prefix}-final-snapshot"

  # Monitoring
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_monitoring.arn

  # Performance Insights (free tier: 7 days)
  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  # Apply changes immediately (acceptable for dev)
  apply_immediately = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-postgres"
  })
}

# ── IAM Role for RDS Enhanced Monitoring ──────────────────────────────────────

resource "aws_iam_role" "rds_monitoring" {
  name = "${local.name_prefix}-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
