###############################################################################
# Step 5: Secrets — Outputs
###############################################################################

output "servicenow_secret_arn" {
  description = "ARN of the ServiceNow credentials secret"
  value       = aws_secretsmanager_secret.servicenow.arn
}

output "servicenow_secret_name" {
  description = "Name of the ServiceNow credentials secret"
  value       = aws_secretsmanager_secret.servicenow.name
}

output "app_secret_arn" {
  description = "ARN of the application secrets (JWT, admin password)"
  value       = aws_secretsmanager_secret.app.arn
}

output "app_secret_name" {
  description = "Name of the application secrets"
  value       = aws_secretsmanager_secret.app.name
}

output "next_steps" {
  description = "Reminder to populate real ServiceNow credentials"
  value       = "IMPORTANT: Update rexus/dev/servicenow with real SN_CLIENT_ID, SN_CLIENT_SECRET, SN_INSTANCE values before deploying ECS."
}
