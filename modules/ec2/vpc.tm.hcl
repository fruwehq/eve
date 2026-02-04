generate_hcl "z_ec2_vpc.tf" {
  content {
    resource "aws_default_vpc" "default" {
      tags = tm_merge(global.aws.tags, {
        Environment = global.environment
        Name = "Default VPC"
      })
    }
  }
}
