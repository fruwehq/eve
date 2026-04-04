globals "aws" {
  region = "ap-northeast-1"

  tags = {
    Project   = global.project_name
    ManagedBy = "terraform"
  }

  security_group = {
    name = "ephemeral-cloud-gaming-windows"
  }
}
