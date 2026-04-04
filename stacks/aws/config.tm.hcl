globals "aws" {
  region = "ap-northeast-1"

  tags = {
    Project   = global.project
    ManagedBy = "terraform"
  }

  security_group = {
    name = "ephemeral-cloud-gaming-windows"
  }
}
