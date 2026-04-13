###############################################################################
# Step 6: ECS — Outputs
###############################################################################

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "backend_service_name" {
  description = "ECS backend service name"
  value       = aws_ecs_service.backend.name
}

output "frontend_service_name" {
  description = "ECS frontend service name"
  value       = aws_ecs_service.frontend.name
}

output "backend_task_definition_arn" {
  description = "Backend task definition ARN (latest revision)"
  value       = aws_ecs_task_definition.backend.arn
}

output "frontend_task_definition_arn" {
  description = "Frontend task definition ARN (latest revision)"
  value       = aws_ecs_task_definition.frontend.arn
}

output "ecs_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN (used by application code)"
  value       = aws_iam_role.ecs_task.arn
}

output "backend_log_group" {
  description = "CloudWatch log group for the backend service"
  value       = aws_cloudwatch_log_group.backend.name
}

output "frontend_log_group" {
  description = "CloudWatch log group for the frontend service"
  value       = aws_cloudwatch_log_group.frontend.name
}

output "ecs_exec_command" {
  description = "Example command to exec into a running backend task (replace TASK_ID)"
  value       = "aws ecs execute-command --cluster ${aws_ecs_cluster.main.name} --task TASK_ID --container backend --interactive --command /bin/bash"
}
