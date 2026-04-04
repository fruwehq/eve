generate_hcl "z_vultr_instance.tf" {
  content {
    data "vultr_reserved_ip" "default" {
      filter {
        name   = "label"
        values = [global.vultr.reserved_ip.label]
      }
    }

    resource "vultr_startup_script" "windows_ssh" {
      name = "windows-ssh-bootstrap"
      type = "boot"
      script = base64encode(templatefile(
        "${terramate.root.path.fs.absolute}/windows/ssh.ps1.tftpl",
        {
          public_key = trimspace(file(pathexpand(local.ssh_public_key_file)))
        }
      ))
    }

    resource "vultr_instance" "default" {
      backups        = global.vultr.instance.backups
      os_id          = global.vultr.instance.os_id
      plan           = global.vultr.instance.plan
      region         = global.vultr.region
      reserved_ip_id = data.vultr_reserved_ip.default.id
      script_id      = vultr_startup_script.windows_ssh.id
    }

    output "vultr_instance_default_password" {
      description = "Default password returned by Vultr for the created instance"
      value       = vultr_instance.default.default_password
      sensitive   = true
    }

    output "vultr_instance_main_ip" {
      value = vultr_instance.default.main_ip
    }
  }
}
