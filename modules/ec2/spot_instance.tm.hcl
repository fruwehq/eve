generate_hcl "z_ec2_spot_instance.tf" {
  content {
    locals {
      use_spot = try(global.use_spot, false)
      spot_interruption_behavior = "stop"
    }
  }
}
