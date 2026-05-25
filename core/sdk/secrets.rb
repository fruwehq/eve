# frozen_string_literal: true

require "yaml"
require "fileutils"

module Eve
  module SDK
    module Secrets
      class SecretsError < StandardError; end

      def self.secrets_dir
        dir = ENV["EVE_SECRETS_DIR"]
        dir && !dir.empty? ? File.expand_path(dir) : File.join(Workdir.eve_dir, "secrets")
      end

      def self.path_for(provider_id)
        File.join(secrets_dir, "#{provider_id}.yaml")
      end

      def self.lock_path(provider_id)
        File.join(secrets_dir, "#{provider_id}.lock")
      end

      def self.ensure_secrets_dir
        Workdir.ensure_dir(secrets_dir)
      end

      def self.with_read_lock(provider_id)
        ensure_secrets_dir
        AtomicYaml.with_lock(lock_path(provider_id)) do
          yield
        end
      end

      def self.with_write_lock(provider_id)
        ensure_secrets_dir
        AtomicYaml.with_lock(lock_path(provider_id)) do
          yield
        end
      end

      def self.read(provider_id)
        path = path_for(provider_id)
        with_read_lock(provider_id) do
          return {} unless File.exist?(path)

          raw = File.read(path)
          return {} if raw.strip.empty?

          parsed = YAML.safe_load(raw, permitted_classes: [Symbol])
          unless parsed.is_a?(Hash) && parsed.key?(provider_id)
            raise SecretsError, "Secrets file #{path} must have top-level key '#{provider_id}'"
          end

          secrets = parsed[provider_id]
          unless secrets.is_a?(Hash)
            raise SecretsError, "Secrets file #{path}: '#{provider_id}' must be a mapping"
          end

          secrets.each do |k, v|
            next if v.nil?
            unless v.is_a?(String)
              raise SecretsError, "Secret '#{provider_id}.#{k}' must be a string, got #{v.class}"
            end
          end

          secrets
        end
      rescue Psych::SyntaxError => e
        raise SecretsError, "Cannot parse secrets for #{provider_id}: #{e.message}"
      end

      def self.write(provider_id, hash)
        validate_values!(provider_id, hash)
        path = path_for(provider_id)
        ensure_secrets_dir

        with_write_lock(provider_id) do
          AtomicYaml.atomic_write(path, provider_id => hash)
          File.chmod(0o600, path)
        end

        hash
      end

      def self.update(provider_id, partial)
        with_write_lock(provider_id) do
          path = path_for(provider_id)
          current = AtomicYaml.load_yaml(path)

          current[provider_id] ||= {}
          partial.each do |k, v|
            if v.nil?
              current[provider_id].delete(k.to_s)
            else
              current[provider_id][k.to_s] = v
            end
          end

          validate_values!(provider_id, current[provider_id])
          AtomicYaml.atomic_write(path, current)
          File.chmod(0o600, path) if File.exist?(path)
          current[provider_id]
        end
      end

      def self.delete(provider_id, keys: :all)
        path = path_for(provider_id)
        return unless File.exist?(path)

        if keys == :all
          with_write_lock(provider_id) do
            File.delete(path) if File.exist?(path)
          end
          return
        end

        with_write_lock(provider_id) do
          current = AtomicYaml.load_yaml(path)

          current[provider_id] ||= {}
          Array(keys).each { |k| current[provider_id].delete(k.to_s) }

          if current[provider_id].empty?
            File.delete(path) if File.exist?(path)
          else
            AtomicYaml.atomic_write(path, current)
            File.chmod(0o600, path) if File.exist?(path)
          end
        end
      end

      def self.modify(provider_id)
        ensure_secrets_dir

        with_write_lock(provider_id) do
          path = path_for(provider_id)
          current = AtomicYaml.load_yaml(path)

          current[provider_id] ||= {}
          result = yield(current[provider_id].dup)
          validate_values!(provider_id, result)
          current[provider_id] = result
          AtomicYaml.atomic_write(path, current)
          File.chmod(0o600, path) if File.exist?(path)
          result
        end
      end

      def self.get(provider_id, key)
        secrets = read(provider_id)
        secrets[key.to_s]
      end

      def self.keys_set(provider_id)
        path = path_for(provider_id)
        with_read_lock(provider_id) do
          return [] unless File.exist?(path)

          raw = File.read(path)
          return [] if raw.strip.empty?

          parsed = YAML.safe_load(raw, permitted_classes: [Symbol])
          return [] unless parsed.is_a?(Hash) && parsed.key?(provider_id)

          secrets = parsed[provider_id]
          return [] unless secrets.is_a?(Hash)

          secrets.each do |k, v|
            next if v.nil?
            unless v.is_a?(String)
              raise SecretsError, "Secret '#{provider_id}.#{k}' must be a string, got #{v.class}"
            end
          end

          secrets.keys
        end
      rescue Psych::SyntaxError => e
        raise SecretsError, "Cannot parse secrets for #{provider_id}: #{e.message}"
      end

      def self.validate_values!(provider_id, hash)
        return if hash.nil? || hash.empty?

        hash.each do |k, v|
          next if v.nil?
          unless v.is_a?(String)
            raise SecretsError, "Secret '#{provider_id}.#{k}' must be a string, got #{v.class}"
          end
        end
      end
    end
  end
end
