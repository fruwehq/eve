generate_hcl "z_vultr_instance.tf" {
  content {
    data "vultr_reserved_ip" "default" {
      filter {
        name   = "label"
        values = [global.vultr.reserved_ip.label]
      }
    }

    resource "vultr_instance" "default" {
      backups        = global.vultr.instance.backups
      os_id          = global.vultr.instance.os_id
      plan           = global.vultr.instance.plan
      region         = global.vultr.region
      reserved_ip_id = data.vultr_reserved_ip.default.id
    }

    output "vultr_instance_default_password" {
      description = "Default password returned by Vultr for the created instance"
      value       = vultr_instance.default.default_password
      sensitive   = true
    }
  }
}
