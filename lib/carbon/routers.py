import imp
from carbon.relayrules import loadRelayRules
from carbon.hashing import ConsistentHashRing


class DatapointRouter:
  "Interface for datapoint routing logic implementations"

  def addDestination(self, destination):
    "destination is a (host, port, instance) triple"

  def removeDestination(self, destination):
    "destination is a (host, port, instance) triple"

  def getDestinations(self, key):
    "generate a (host, port) for each of the given key's destinations"


class RelayRulesRouter(DatapointRouter):
  def __init__(self, rules_path):
    self.rules_path = rules_path
    self.rules = loadRelayRules()
    self.destinations = set()

  def addDestination(self, destination):
    self.destinations.add(destination)

  def removeDestination(self, destination):
    self.destinations.discard(destination)

  def getDestinations(self, key):
    for rule in self.rules:
      if rule.matches(key):
        for destination in rule.destinations:
          if destination in self.destinations:
            yield destination


class ConsistentHashingRouter(DatapointRouter):
  def __init__(self, replication_factor=1):
    self.replication_factor = int(replication_factor)
    self.instance_ports = {} # { (server, instance) : port }
    self.ring = ConsistentHashRing([])

  def addDestination(self, destination):
    (server, port, instance) = destination
    if (server, instance) in self.instance_ports:
      raise Exception("destination instance (%s, %s) already configured" % (server, instance))
    self.instance_ports[ (server, instance) ] = port
    self.ring.add_node( (server, instance) )

  def removeDestination(self, destination):
    (server, port, instance) = destination
    if (server, instance) not in self.instance_ports:
      raise Exception("destination instance (%s, %s) not configured" % (server, instance))
    del self.instance_ports[ (server, instance) ]
    self.ring.remove_node( (server, instance) )

  def getDestinations(self, metric):
    key = self.getKey(metric)

    used_servers = set()
    for (server, instance) in self.ring.get_nodes(key):
      if server in used_servers:
        continue
      else:
        used_servers.add(server)
        port = self.instance_ports[ (server, instance) ]
        yield (server, port)

      if len(used_servers) >= self.replication_factor:
        return

  def getKey(self, metric):
    return metric

  def setKeyFunction(self, func):
    self.getKey = func

  def setKeyFunctionFromModule(self, keyfunc_spec):
    module_path, func_name = keyfunc_spec.rsplit(':', 1)
    module_file = open(module_path, 'U')
    description = ('.py', 'U', imp.PY_SOURCE)
    module = imp.load_module('keyfunc_module', module_file, module_path, description)
    keyfunc = getattr(module, func_name)
    self.setKeyFunction(keyfunc)
