# Auto included into 10-base stack
# Executed AFTER __init__.tm.hcl - Use this for shared configuration such as secrets

generate_hcl "z_windows_late_init.tf" {
  content {
  }
}
