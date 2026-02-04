generate_hcl "z_ec2_common_data.tf" {
  content {
    data "aws_vpc" "default" {
      default = true
    }
  }
}
