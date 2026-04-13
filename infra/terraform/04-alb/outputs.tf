###############################################################################
# Step 4: ALB — Outputs
###############################################################################

output "alb_dns_name" {
  description = "ALB DNS name — use this as your application endpoint"
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.main.arn
}

output "alb_zone_id" {
  description = "ALB Route 53 hosted zone ID (for alias records)"
  value       = aws_lb.main.zone_id
}

output "alb_name" {
  description = "ALB name"
  value       = aws_lb.main.name
}

output "http_listener_arn" {
  description = "HTTP listener ARN (port 80)"
  value       = aws_lb_listener.http.arn
}

output "backend_target_group_arn" {
  description = "ARN of the backend ECS target group (port 8000)"
  value       = aws_lb_target_group.backend.arn
}

output "backend_target_group_name" {
  description = "Name of the backend target group"
  value       = aws_lb_target_group.backend.name
}

output "frontend_target_group_arn" {
  description = "ARN of the frontend ECS target group (port 80)"
  value       = aws_lb_target_group.frontend.arn
}

output "frontend_target_group_name" {
  description = "Name of the frontend target group"
  value       = aws_lb_target_group.frontend.name
}

output "app_url" {
  description = "Application base URL"
  value       = "http://${aws_lb.main.dns_name}"
}
