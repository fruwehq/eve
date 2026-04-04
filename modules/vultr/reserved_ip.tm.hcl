generate_hcl "z_vultr_reserved_ip.tf" {
  content {
    resource "vultr_reserved_ip" "default" {
      label   = global.reserved_ip.label
      region  = global.vultr.region
      ip_type = "v4"
    }
  }
}
