import 'dart:io';

import 'package:args/args.dart';
import 'package:wash_server/server/server.dart';

const String bindHost = '127.0.0.1';

void main(List<String> arguments) async {
  final parser = ArgParser()
    ..addOption('root', help: 'project root directory', mandatory: true)
    ..addOption('port',
        help: 'TCP port (0 = ephemeral)', defaultsTo: '0');

  ArgResults args;
  try {
    args = parser.parse(arguments);
  } catch (e) {
    stderr.writeln('error: $e');
    stderr.writeln(parser.usage);
    exitCode = 1;
    return;
  }

  final rootPath = args['root'] as String;
  final portArg = int.tryParse(args['port'] as String) ?? 0;

  final rootDir = Directory(rootPath);
  if (!rootDir.existsSync()) {
    stderr.writeln('error: root is not a directory: $rootPath');
    exitCode = 1;
    return;
  }

  final (server, boundPort) = await createServer(rootPath, bindHost, portArg);

  if (portArg == 0) {
    stdout.writeln('WASH-PORT $boundPort');
    stdout.flush();
  }

  // Handle SIGTERM gracefully
  ProcessSignal.sigterm.watch().listen((_) async {
    await server.close();
    exit(0);
  });

  await server.serve();
}
