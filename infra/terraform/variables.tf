variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name — used as prefix for all resource names"
  type        = string
  default     = "rexus"
}

variable "environment" {
  description = "Environment: dev, staging, prod"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t4g.medium"  # 2 vCPU, 4GB RAM — sufficient for dev. Use db.r6g.xlarge for prod.
}

variable "db_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 50
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "rexus"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "rexus"
}

variable "ecs_backend_cpu" {
  description = "Backend task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "ecs_backend_memory" {
  description = "Backend task memory in MiB"
  type        = number
  default     = 2048
}

variable "ecs_frontend_cpu" {
  description = "Frontend task CPU units"
  type        = number
  default     = 512
}

variable "ecs_frontend_memory" {
  description = "Frontend task memory in MiB"
  type        = number
  default     = 1024
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "rexus"
    ManagedBy   = "terraform"
  }
}
