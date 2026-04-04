generate_hcl "z_vultr_instance.tf" {
  content {
    data "vultr_reserved_ip" "default" {
      filter {
        name   = "label"
        values = [global.vultr.reserved_ip.label]
      }
    }

    resource "vultr_instance" "default" {
      backup         = global.vultr.instance.backup
      os_id          = global.vultr.instance.os_id
      plan           = global.vultr.instance.plan
      region         = global.vultr.region
      reserved_ip_id = vultr_reserved_ip.default.id
    }
  }
}
