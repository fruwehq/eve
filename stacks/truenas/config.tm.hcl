globals "truenas" {
  pool   = "main"
  bridge = "br0"

  tags = {
    Project   = global.project
    ManagedBy = "terraform"
  }
}
