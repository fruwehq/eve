stack {
  name = "TrueNAS Shared Networking"

  tags = [
    "truenas",
    "truenas-shared",
    "networking",
    "shared",
  ]
}

# TrueNAS networking is managed on the host (bridge, VLANs, etc.).
# This stack exists for future network-scoped resources (e.g., DHCP reservations,
# DNS overrides) and as a dependency anchor for service stacks.
generate_hcl "z_truenas_networking_placeholder.tf" {
  content {
    resource "terraform_data" "truenas_networking_placeholder" {
      input = {
        provider = "truenas"
        note     = "networking scaffold"
      }
    }
  }
}
