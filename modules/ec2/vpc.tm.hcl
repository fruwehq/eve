generate_hcl "z_ec2_vpc.tf" {
  content {
    resource "aws_default_vpc" "default" {
      tags = global.aws.tags
    }
  }
}
