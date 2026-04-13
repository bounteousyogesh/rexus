###############################################################################
# Step 3: ECR — Outputs
###############################################################################

output "backend_repository_url" {
  description = "ECR repository URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_repository_name" {
  description = "ECR repository name for the backend"
  value       = aws_ecr_repository.backend.name
}

output "backend_repository_arn" {
  description = "ECR repository ARN for the backend"
  value       = aws_ecr_repository.backend.arn
}

output "frontend_repository_url" {
  description = "ECR repository URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "frontend_repository_name" {
  description = "ECR repository name for the frontend"
  value       = aws_ecr_repository.frontend.name
}

output "frontend_repository_arn" {
  description = "ECR repository ARN for the frontend"
  value       = aws_ecr_repository.frontend.arn
}

output "aws_account_id" {
  description = "AWS account ID (derived from ECR URL)"
  value       = split(".", aws_ecr_repository.backend.repository_url)[0]
}

output "ecr_registry_url" {
  description = "ECR registry base URL (for docker login)"
  value       = "${split("/", aws_ecr_repository.backend.repository_url)[0]}"
}
