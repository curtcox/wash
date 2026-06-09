import 'dart:convert';
import 'dart:io';

const Set<String> recognizedFields = {
  'arity',
  'input',
  'output',
  'methods',
  'mime',
  'mutates',
  'parse-mode',
  'stderr',
  'exit',
};

const Set<String> validInput = {'stdin'};
const Set<String> validOutput = {'stdout'};
const Set<String> validStderr = {'discard', 'merge'};
const Set<String> validParseMode = {'normal', 'raw'};
const Set<String> reservedInput = {'file', 'none'};
const Set<String> reservedOutput = {'file'};

final _rangeArityRe = RegExp(r'^\d+\.\.\*?$|^\d+\.\.\d+$');

class ExitMapping {
  final Map<int, int> explicit;
  final int? wildcard;

  ExitMapping({Map<int, int>? explicit, this.wildcard})
      : explicit = explicit ?? {};
}

class CommandMetadata {
  Object arity; // int or '*'
  String inputMode;
  String outputMode;
  List<String> methods;
  String? mime;
  bool mutates;
  String parseMode;
  String stderrMode;
  ExitMapping exitMapping;
  bool malformed;
  String? malformedReason;

  CommandMetadata({
    this.arity = 0,
    this.inputMode = 'stdin',
    this.outputMode = 'stdout',
    List<String>? methods,
    this.mime,
    this.mutates = false,
    this.parseMode = 'normal',
    this.stderrMode = 'discard',
    ExitMapping? exitMapping,
    this.malformed = false,
    this.malformedReason,
  })  : methods = methods ?? ['GET'],
        exitMapping = exitMapping ?? ExitMapping();

  bool get invalid => malformed;
}

bool? _parseBool(String value) {
  if (value == 'true') return true;
  if (value == 'false') return false;
  return null;
}

(ExitMapping?, String?) _parseExitPairs(List<String> tokens) {
  final explicit = <int, int>{};
  int? wildcard;
  for (final token in tokens) {
    if (!token.contains('=')) {
      return (null, 'malformed exit pair: $token');
    }
    final eqIdx = token.indexOf('=');
    final codeStr = token.substring(0, eqIdx);
    final statusStr = token.substring(eqIdx + 1);
    final status = int.tryParse(statusStr);
    if (status == null) {
      return (null, 'malformed exit status: $statusStr');
    }
    if (codeStr == '*') {
      wildcard = status;
    } else {
      final code = int.tryParse(codeStr);
      if (code == null) {
        return (null, 'malformed exit code: $codeStr');
      }
      if (code < 0) {
        return (null, 'negative exit code: $codeStr');
      }
      explicit[code] = status;
    }
  }
  return (ExitMapping(explicit: explicit, wildcard: wildcard), null);
}

String? _applyField(CommandMetadata meta, String name, List<String> values) {
  if (name == 'arity') {
    if (values.length != 1) return 'arity requires exactly one value';
    final val = values[0];
    if (val == '*') {
      meta.arity = '*';
      return null;
    }
    if (_rangeArityRe.hasMatch(val)) {
      return 'reserved range arity: $val';
    }
    final n = int.tryParse(val);
    if (n == null) return 'malformed arity: $val';
    if (n < 0) return 'negative arity: $n';
    meta.arity = n;
    return null;
  }

  if (name == 'input') {
    if (values.length != 1) return 'input requires exactly one value';
    final val = values[0];
    if (reservedInput.contains(val)) return 'reserved input mode: $val';
    if (!validInput.contains(val)) return 'malformed input: $val';
    meta.inputMode = val;
    return null;
  }

  if (name == 'output') {
    if (values.length != 1) return 'output requires exactly one value';
    final val = values[0];
    if (reservedOutput.contains(val)) return 'reserved output mode: $val';
    if (!validOutput.contains(val)) return 'malformed output: $val';
    meta.outputMode = val;
    return null;
  }

  if (name == 'methods') {
    if (values.isEmpty) return 'methods requires at least one value';
    meta.methods = List<String>.from(values);
    return null;
  }

  if (name == 'mime') {
    if (values.length != 1) return 'mime requires exactly one value';
    final val = values[0];
    if (!val.contains('/') || val.trim() != val || val.isEmpty) {
      return 'malformed mime: $val';
    }
    meta.mime = val;
    return null;
  }

  if (name == 'mutates') {
    if (values.length != 1) return 'mutates requires exactly one value';
    final parsed = _parseBool(values[0]);
    if (parsed == null) return 'malformed mutates: ${values[0]}';
    meta.mutates = parsed;
    return null;
  }

  if (name == 'parse-mode') {
    if (values.length != 1) return 'parse-mode requires exactly one value';
    final val = values[0];
    if (!validParseMode.contains(val)) return 'malformed parse-mode: $val';
    meta.parseMode = val;
    return null;
  }

  if (name == 'stderr') {
    if (values.length != 1) return 'stderr requires exactly one value';
    final val = values[0];
    if (!validStderr.contains(val)) return 'malformed stderr: $val';
    meta.stderrMode = val;
    return null;
  }

  if (name == 'exit') {
    final (mapping, err) = _parseExitPairs(values);
    if (err != null) return err;
    meta.exitMapping = mapping!;
    return null;
  }

  return null;
}

CommandMetadata loadMetadata(String root, String commandName) {
  final meta = CommandMetadata();
  final metaPath =
      '$root${Platform.pathSeparator}env${Platform.pathSeparator}meta${Platform.pathSeparator}$commandName';
  final metaFile = File(metaPath);
  if (!metaFile.existsSync()) return meta;

  String text;
  try {
    text = metaFile.readAsStringSync(encoding: utf8);
  } catch (e) {
    meta.malformed = true;
    meta.malformedReason = 'failed to read metadata file';
    return meta;
  }

  final fields = <String, List<String>>{};
  for (final line in text.split('\n')) {
    final stripped = line.trim();
    if (stripped.isEmpty) continue;
    if (stripped[0] == '#') continue;
    final parts = stripped.split(RegExp(r'\s+'));
    if (parts.isEmpty) continue;
    final fieldName = parts[0];
    if (!recognizedFields.contains(fieldName)) continue;
    fields[fieldName] = parts.sublist(1);
  }

  for (final entry in fields.entries) {
    final err = _applyField(meta, entry.key, entry.value);
    if (err != null) {
      meta.malformed = true;
      meta.malformedReason = err;
      return meta;
    }
  }

  if (meta.methods.contains('GET') && meta.mutates) {
    meta.malformed = true;
    meta.malformedReason = 'GET permitted with mutates true';
    return meta;
  }

  return meta;
}

CommandMetadata defaultMetadata() => CommandMetadata();

int mapExitStatus(CommandMetadata meta, int exitCode) {
  if (exitCode == 0) {
    final explicit = meta.exitMapping.explicit[0];
    if (explicit != null) return explicit;
    return 200;
  }
  final explicit = meta.exitMapping.explicit[exitCode];
  if (explicit != null) return explicit;
  if (meta.exitMapping.wildcard != null) return meta.exitMapping.wildcard!;
  return 400;
}

bool methodPermitted(CommandMetadata meta, String method) {
  return meta.methods.contains(method);
}

bool headPermitted(CommandMetadata meta) {
  return meta.methods.contains('GET') || meta.methods.contains('HEAD');
}
