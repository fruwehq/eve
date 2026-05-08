generate_hcl "z_ec2_vpc.tf" {
  content {
    resource "aws_default_vpc" "default" {
      tags = tm_merge(global.aws.tags, {
        Environment = global.project
        Name        = "Default VPC"
      })
    }
  }
}
