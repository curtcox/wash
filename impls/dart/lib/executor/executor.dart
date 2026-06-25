import 'dart:io';
import 'dart:async';

import '../filesystem/filesystem.dart';
import '../metadata/metadata.dart';
import '../parser/parser.dart';
import 'package:glob/glob.dart';

class ExecutionError implements Exception {
  final String message;
  final int status;

  ExecutionError(this.message, {this.status = 500});

  @override
  String toString() => 'ExecutionError($status): $message';
}

class ExecRule {
  final String pattern;
  final String interpreter;
  final List<String> extraArgs;

  ExecRule(
      {required this.pattern,
      required this.interpreter,
      required this.extraArgs});
}

class StageResult {
  final String name;
  final int exitCode;
  final List<int> stdout;
  final List<int> stderr;
  final int httpStatus;

  StageResult({
    required this.name,
    required this.exitCode,
    required this.stdout,
    required this.stderr,
    required this.httpStatus,
  });
}

class PipelineResult {
  final List<int> stdout;
  final List<int> stderr;
  final String contentType;
  final List<StageResult> stages;
  final String pipelineDescription;
  final String? sourcePath;
  final String? finalCommand;
  final StageResult? failingStage;
  final int httpStatus;

  PipelineResult({
    required this.stdout,
    required this.stderr,
    required this.contentType,
    required this.stages,
    required this.pipelineDescription,
    required this.sourcePath,
    this.finalCommand,
    this.failingStage,
    this.httpStatus = 200,
  });
}

class ExecConfig {
  final List<ExecRule> rules;
  final bool malformed;
  final String? malformedReason;

  ExecConfig(this.rules, {this.malformed = false, this.malformedReason});
}

ExecConfig loadExecRules(String root) {
  final execFile = File('$root${Platform.pathSeparator}exec');
  final rules = <ExecRule>[];
  if (!execFile.existsSync()) return ExecConfig(rules);

  for (final line in execFile.readAsLinesSync()) {
    final stripped = line.trim();
    if (stripped.isEmpty || stripped.startsWith('#')) continue;
    final parts = stripped.split(RegExp(r'\s+'));
    if (parts.length < 2) {
      return ExecConfig(
        rules,
        malformed: true,
        malformedReason: 'malformed exec rule: $line',
      );
    }
    rules.add(ExecRule(
      pattern: parts[0],
      interpreter: parts[1],
      extraArgs: parts.sublist(2),
    ));
  }
  return ExecConfig(rules);
}

bool _hasGlob(String pattern) {
  return pattern.contains('*') ||
      pattern.contains('?') ||
      pattern.contains('[');
}

bool _ruleMatches(ExecRule rule, String commandPath, String commandDir) {
  final basename = commandPath.split(Platform.pathSeparator).last;
  if (!_hasGlob(rule.pattern)) {
    return basename == rule.pattern;
  }
  String rel;
  try {
    rel = commandPath
        .replaceFirst(commandDir, '')
        .replaceFirst(RegExp(r'^[/\\]'), '');
    rel = rel.replaceAll('\\', '/');
  } catch (_) {
    rel = basename;
  }
  final globBasename = Glob(rule.pattern);
  final globRel = Glob(rule.pattern);
  return globBasename.matches(basename) || globRel.matches(rel);
}

List<String> resolveInvocation(
  String commandPath,
  List<String> commandDirs,
  ExecConfig execConfig,
) {
  if (execConfig.malformed) {
    throw ExecutionError(
      execConfig.malformedReason ?? 'malformed exec rules',
      status: 500,
    );
  }

  final file = File(commandPath);
  if (file.existsSync()) {
    final stat = file.statSync();
    // Check executable bit (mode & 0o111)
    if ((stat.mode & 0x49) != 0) {
      return [commandPath];
    }
  }

  String? commandDir;
  for (final dir in commandDirs) {
    if (commandPath.startsWith(dir)) {
      commandDir = dir;
      break;
    }
  }
  commandDir ??=
      commandPath.substring(0, commandPath.lastIndexOf(Platform.pathSeparator));

  for (final rule in execConfig.rules) {
    if (_ruleMatches(rule, commandPath, commandDir)) {
      if (rule.interpreter == '__wash_missing_interpreter__') {
        throw ExecutionError(
          'unresolved interpreter for command ${commandPath.split(Platform.pathSeparator).last}',
          status: 500,
        );
      }
      return [rule.interpreter, ...rule.extraArgs, commandPath];
    }
  }

  if (file.existsSync()) {
    return [commandPath];
  }

  throw ExecutionError(
    'could not resolve interpreter for command ${commandPath.split(Platform.pathSeparator).last}',
    status: 500,
  );
}

bool _stderrMergeEnabled(CommandStage stage) {
  return stage.stderrMergeBoundary || stage.metadata.stderrMode == 'merge';
}

Future<(int, List<int>, List<int>)> _runProcess(
  List<String> argv, {
  required String cwd,
  required List<int>? stdinData,
  required bool mergeStderr,
}) async {
  final process = await Process.start(
    argv[0],
    argv.sublist(1),
    workingDirectory: cwd,
    environment: {
      ...Platform.environment,
    },
  );

  if (stdinData != null && stdinData.isNotEmpty) {
    process.stdin.add(stdinData);
  }
  await process.stdin.close();

  final stdoutFuture =
      process.stdout.fold<List<int>>([], (prev, chunk) => [...prev, ...chunk]);
  if (mergeStderr) {
    // stderr is already merged into stdout by redirecting stderr to stdout
    // We need a different approach: use process.stderr and interleave
    // For merge, we collect stderr separately but append to stdout result
    final stderrFuture = process.stderr
        .fold<List<int>>([], (prev, chunk) => [...prev, ...chunk]);
    final exitCode = await process.exitCode;
    final stdoutBytes = await stdoutFuture;
    final stderrBytes = await stderrFuture;
    return (exitCode, [...stdoutBytes, ...stderrBytes], <int>[]);
  } else {
    final stderrFuture = process.stderr
        .fold<List<int>>([], (prev, chunk) => [...prev, ...chunk]);
    final exitCode = await process.exitCode;
    final stdoutBytes = await stdoutFuture;
    final stderrBytes = await stderrFuture;
    return (exitCode, stdoutBytes, stderrBytes);
  }
}

Future<PipelineResult> executeRawCommand(
  RawCommandParse raw, {
  required String root,
  required List<String> commandDirs,
  required ExecConfig execConfig,
  required String method,
  required List<int> body,
}) async {
  final stage = raw.stage;
  final invocation =
      resolveInvocation(stage.commandPath, commandDirs, execConfig);
  final fullInvocation = [...invocation, raw.rawSuffix];
  final stdinData = body.isNotEmpty ? body : null;
  final (exitCode, stdout, stderr) = await _runProcess(
    fullInvocation,
    cwd: root,
    stdinData: stdinData,
    mergeStderr: _stderrMergeEnabled(stage),
  );
  final httpStatus = mapExitStatus(stage.metadata, exitCode);
  final stageResult = StageResult(
    name: stage.name,
    exitCode: exitCode,
    stdout: stdout,
    stderr: stderr,
    httpStatus: httpStatus,
  );
  final contentType = stage.metadata.mime ?? 'text/plain';
  return PipelineResult(
    stdout: stdout,
    stderr: stderr,
    contentType: contentType,
    stages: [stageResult],
    pipelineDescription: '${stage.name} ${raw.rawSuffix}'.trim(),
    sourcePath: null,
    finalCommand: stage.name,
    failingStage: httpStatus >= 400 ? stageResult : null,
    httpStatus: httpStatus,
  );
}

Future<PipelineResult> executePipeline(
  PipelineParse pipeline, {
  required String root,
  required List<String> commandDirs,
  required ExecConfig execConfig,
  required List<int> body,
  String symlinkPolicy = 'reject-escaping',
  bool caseSensitive = true,
}) async {
  final stages = pipeline.stages;
  if (stages.isEmpty) {
    throw ExecutionError('empty pipeline');
  }

  List<int>? stdinData;
  if (pipeline.inputSuffixRaw != null && pipeline.inputSuffixRaw!.isNotEmpty) {
    try {
      stdinData = impliedCatBytes(
        root,
        pipeline.inputSuffixRaw!,
        symlinkPolicy: symlinkPolicy,
        caseSensitive: caseSensitive,
      );
    } on FileSystemException catch (e) {
      final msg = e.message.toLowerCase();
      if (msg.contains('not found') || msg.contains('no such')) {
        throw ExecutionError(e.message, status: 404);
      }
      if (msg.contains('directory')) {
        throw ExecutionError(e.message, status: 400);
      }
      if (msg.contains('escapes root') || msg.contains('not permitted')) {
        throw ExecutionError(e.message, status: 403);
      }
      throw ExecutionError(e.message, status: 404);
    } on NameEscapeError {
      throw ExecutionError('path not permitted', status: 403);
    } on NameLoopError {
      throw ExecutionError('name resolution loop detected', status: 508);
    } on RootEscapeError {
      throw ExecutionError('path not permitted', status: 403);
    } on SymlinkEscapeError {
      throw ExecutionError('path not permitted', status: 403);
    }
  } else if (body.isNotEmpty) {
    stdinData = body;
  }

  final dataFlowStages = stages.reversed.toList();
  final stageResults = <StageResult>[];
  List<int>? currentInput = stdinData;

  for (final stage in dataFlowStages) {
    final invocation =
        resolveInvocation(stage.commandPath, commandDirs, execConfig);
    final fullInvocation = [...invocation, ...stage.argv];
    final merge = _stderrMergeEnabled(stage);
    final (exitCode, stdout, stderr) = await _runProcess(
      fullInvocation,
      cwd: root,
      stdinData: currentInput,
      mergeStderr: merge,
    );
    final httpStatus = mapExitStatus(stage.metadata, exitCode);
    final result = StageResult(
      name: stage.name,
      exitCode: exitCode,
      stdout: stdout,
      stderr: stderr,
      httpStatus: httpStatus,
    );
    stageResults.add(result);
    currentInput = stdout;
  }

  final firstFail = _firstFailingInUrlOrder(stages, stageResults);
  if (firstFail != null) {
    return PipelineResult(
      stdout: firstFail.stdout,
      stderr: firstFail.stderr,
      contentType: _finalContentType(stages),
      stages: stageResults,
      pipelineDescription: pipeline.pipelineDescription,
      sourcePath: pipeline.sourcePath,
      finalCommand: stages.isNotEmpty ? stages[0].name : null,
      failingStage: firstFail,
      httpStatus: firstFail.httpStatus,
    );
  }

  final finalStage = stages[0];
  final contentType = finalStage.metadata.mime ?? 'text/plain';
  return PipelineResult(
    stdout: currentInput ?? [],
    stderr: [],
    contentType: contentType,
    stages: stageResults,
    pipelineDescription: pipeline.pipelineDescription,
    sourcePath: pipeline.sourcePath,
    finalCommand: stages.isNotEmpty ? stages[0].name : null,
    failingStage: null,
    httpStatus: 200,
  );
}

StageResult? _firstFailingInUrlOrder(
  List<CommandStage> urlStages,
  List<StageResult> dataFlowResults,
) {
  final byName = <String, StageResult>{};
  for (final r in dataFlowResults) {
    byName[r.name] = r;
  }
  for (final stage in urlStages) {
    final result = byName[stage.name];
    if (result != null && result.httpStatus >= 400) {
      return result;
    }
  }
  return null;
}

String _finalContentType(List<CommandStage> stages) {
  if (stages.isNotEmpty) {
    return stages[0].metadata.mime ?? 'text/plain';
  }
  return 'text/plain';
}
