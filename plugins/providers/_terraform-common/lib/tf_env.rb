# frozen_string_literal: true

require "json"

module EveProviderTfEnv
  module_function

  def env
    JSON.parse(ENV.fetch("EVE_TF_ENV_JSON"))
  end

  def quote(value)
    "'" + value.to_s.gsub("'", "'\\''") + "'"
  end

  def print_kv(key, value)
    puts "export #{key}=#{quote(value)};"
  end

  def normalize_path(value)
    return value if value.nil? || value.empty?

    home = ENV["HOME"].to_s
    case value
    when "~"
      home
    when /\A~\// then home + value[1..]
    when "$HOME"
      home
    when /\A\$HOME\// then home + value[5..]
    when "$(HOME)"
      home
    when /\A\$\(HOME\)\// then home + value[7..]
    else value
    end
  end
end
