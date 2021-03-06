import os
import subprocess
import argschema
import renderapi
import tempfile
import json

class RenderClientParameters(argschema.schemas.DefaultSchema):
    host = argschema.fields.Str(required=True, description='render host')
    port = argschema.fields.Int(required=True, description='render post integer')
    owner = argschema.fields.Str(required=True, description='render default owner')
    project = argschema.fields.Str(required=True, description='render default project')
    client_scripts = argschema.fields.Str(
        required=True, description='path to render client scripts')
    memGB = argschema.fields.Str(
        required=False, default='5G', description='string describing java heap memory (default 5G)')


class RenderParameters(argschema.ArgSchema):
    render = argschema.fields.Nested(RenderClientParameters)


class RenderTrakEM2Parameters(RenderParameters):
    renderHome = argschema.fields.InputDir(
        required=True, description='root path of standard render install')


class TEM2ProjectTransfer(RenderTrakEM2Parameters):
    minX = argschema.fields.Int(required=True,
                                description='minimum x')
    minY = argschema.fields.Int(required=True,
                                description='minimum y')
    maxX = argschema.fields.Int(required=True,
                                description='maximum x')
    maxY = argschema.fields.Int(required=True,
                                description='maximum y')
    minZ = argschema.fields.Int(required=False,
                                description='minimum z')
    maxZ = argschema.fields.Int(required=False,
                                description='maximum z')
    inputStack = argschema.fields.Str(
        required=True, description='stack to import from')
    outputStack = argschema.fields.Str(
        required=True, description='stack to output to')
    outputXMLdir = argschema.fields.Str(
        required=True, description='path to save xml files')
    doChunk = argschema.fields.Boolean(
        required=False, default=False, description='split the input into chunks')
    chunkSize = argschema.fields.Int(
        required=False, default=50, description='size of chunks')


class EMLMRegistrationParameters(TEM2ProjectTransfer):
    LMstack = argschema.fields.Str(
        required=True, description='name of LM stack to use for registration')
    minX = argschema.fields.Int(
        required=False, description='minimum x (default to EM stack bounds)')
    minY = argschema.fields.Int(
        required=False, description='minimum y (default to EM stack bounds)')
    maxX = argschema.fields.Int(
        required=False, description='maximum x (default to EM stack bounds)')
    maxY = argschema.fields.Int(
        required=False, description='maximum y (default to EM stack bounds)')
    minZ = argschema.fields.Int(
        required=False, description='minimum z (default to EM stack bounds)')
    maxZ = argschema.fields.Int(
        required=False, description='maximum z (default to EM stack bounds)')

class EMLMRegistrationMultiParameters(TEM2ProjectTransfer):
    LMstacks = argschema.fields.List(argschema.fields.Str,
        required=True, description='names of LM stack to use for registration')
    minX = argschema.fields.Int(
        required=False, description='minimum x (default to EM stack bounds)')
    minY = argschema.fields.Int(
        required=False, description='minimum y (default to EM stack bounds)')
    maxX = argschema.fields.Int(
        required=False, description='maximum x (default to EM stack bounds)')
    maxY = argschema.fields.Int(
        required=False, description='maximum y (default to EM stack bounds)')
    minZ = argschema.fields.Int(
        required=False, description='minimum z (default to EM stack bounds)')
    maxZ = argschema.fields.Int(
        required=False, description='maximum z (default to EM stack bounds)')
    buffersize= argschema.fields.Int(
        required=False, default=0, description='Buffer size to add')
    LMstack_index = argschema.fields.Int(required=False, default=0,
                                         description="index of LMstack list to create point matches between")

class RenderModuleException(Exception):
    """Base Exception class for render module"""
    pass


class RenderModule(argschema.ArgSchemaParser):
    default_schema = RenderParameters

    def __init__(self, schema_type=None, *args, **kwargs):
        if (schema_type is not None and not issubclass(
                schema_type, RenderParameters)):
            raise RenderModuleException(
                'schema {} is not of type RenderParameters')

        # TODO do we want output schema passed?
        super(RenderModule, self).__init__(
            schema_type=schema_type, *args, **kwargs)
        self.render = renderapi.render.connect(**self.args['render'])

class TrakEM2RenderModule(RenderModule):
    default_schema = RenderTrakEM2Parameters
    def __init__(self, *args, **kwargs):
        super(TrakEM2RenderModule, self).__init__(*args, **kwargs)
        jarDir = os.path.join(self.args['renderHome'], 'render-app', 'target')
        self.renderjarFile = next(os.path.join(jarDir, f) for f in os.listdir(
            jarDir) if f.endswith('jar-with-dependencies.jar'))
        self.trakem2cmd = ['java', '-cp', self.renderjarFile,
                           'org.janelia.alignment.trakem2.Converter']

    def get_trakem2_tilespecs(self,xmlFile):
        projectPath = os.path.split(xmlFile)[0]
        json_fp = tempfile.NamedTemporaryFile(mode='w',delete=False)
        self.convert_trakem2_project(xmlFile,projectPath,json_fp.name)
        with open(json_fp.name,'r') as fp:
            ts_json = json.load(fp)
        tilespecs = [renderapi.tilespec.TileSpec(json=d) for d in ts_json]
        os.remove(json_fp.name)
        return tilespecs
    
    def convert_trakem2_project(self, xmlFile, projectPath, json_path):
        cmd = self.trakem2cmd + ['%s' % xmlFile, '%s' %
                                 projectPath, '%s' % json_path]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while proc.poll() is None:
            line = proc.stdout.readline()
            if 'ERROR' in line:
                self.logger.error(line)
            else:
                self.logger.debug(line)
        while proc.poll() is None:
            line = proc.stdout.readline()
            if 'ERROR' in line:
                self.logger.error(line)
            else:
                self.logger.debug(line)


if __name__ == '__main__':
    example_input = {
        "render": {
            "host": "ibs-forrestc-ux1",
            "port": 8080,
            "owner": "NewOwner",
            "project": "H1706003_z150",
            "client_scripts": "/pipeline/render/render-ws-java-client/src/main/scripts"
        }
    }
    module = RenderModule(input_data=example_input)

    bad_input = {
        "render": {
            "host": "ibs-forrestc-ux1",
            "port": '8080',
            "owner": "Forrest",
            "project": "H1706003_z150",
            "client_scripts": "/pipeline/render/render-ws-java-client/src/main/scripts"
        }
    }
    module = RenderModule(input_data=bad_input)
