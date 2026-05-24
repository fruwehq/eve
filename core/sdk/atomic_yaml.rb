# frozen_string_literal: true

require "tempfile"
require "yaml"
require "fileutils"

module Eve
  module SDK
    module AtomicYaml
      def self.with_lock(lock_path)
        FileUtils.mkdir_p(File.dirname(lock_path))
        File.open(lock_path, File::RDWR | File::CREAT, 0o600) do |f|
          f.flock(File::LOCK_EX)
          yield
        end
      end

      def self.atomic_write(path, data)
        dir = File.dirname(path)
        FileUtils.mkdir_p(dir)
        tmp = Tempfile.create([".eve-atomic-", ".yaml"], dir)
        begin
          tmp.write(YAML.dump(data))
          tmp.chmod(0o644)
          tmp.close
          File.rename(tmp.path, path)
        rescue StandardError
          tmp.close
          File.delete(tmp.path) if tmp.path && File.exist?(tmp.path)
          raise
        end
      end

      def self.load_yaml(path)
        return {} unless File.exist?(path)

        raw = File.read(path)
        return {} if raw.strip.empty?

        data = YAML.safe_load(raw, permitted_classes: [Symbol])
        data.is_a?(Hash) ? data : {}
      end
    end
  end
end
