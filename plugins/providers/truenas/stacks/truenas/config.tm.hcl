globals {
  terraform_version = "~> 1.14.9"
  project           = "ephemeral-cloud-gaming"
}

globals "truenas" {
  pool   = "main"
  bridge = "br0"

  tags = {
    Project   = global.project
    ManagedBy = "terraform"
  }
}
