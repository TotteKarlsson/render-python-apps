import renderapi
import json
import numpy as np
from functools import partial
import os
import pathos.multiprocessing as mp
from shapely import geometry
import argparse 

example_json = {
    "render":{
        "host":"ibs-forrestc-ux1",
        "port":8080,
        "owner":"Forrest",
        "project":"M247514_Rorb_1",
        "client_scripts":"/pipeline/render/render-ws-java-client/src/main/scripts"
    },
    "stack":"ALIGNDAPI_1_deconv_filter_fix",
    "polygon_dir":"/nas3/data/M247514_Rorb_1/processed/shape_polygons",
    "matchcollection":"M247514_Rorb_1_DAPI1_deconv_filter_fix2",
    "targetmatchcollection":"M247514_Rorb_1_DAPI1_deconv_filter_cropped"
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Filter point matches that start or end outside polygons defined in polygon_dir,\
    that were generated from specified stack")
    parser.add_argument('--inputJson',help='json based input argument file',type=str)
    parser.add_argument('--verbose','-v',help='verbose logging',action='store_true')
    args = parser.parse_args()

    if args.inputJson is None:
        jsonargs = example_json
    else:
        jsonargs = json.load(open(args.inputJson,'r'))

    if args.verbose:
        stripLogger(logging.getLogger())
        logging.basicConfig(level=logging.DEBUG,stream=sys.stdout)
        logging.debug('verbose mode enabled!')

    stack = jsonargs['stack']
    polygonfolder = jsonargs['polygon_dir']
    matchcollection = jsonargs['matchcollection']
    targetmatchcollection =jsonargs['targetmatchcollection']

    r = renderapi.render.connect(**jsonargs['render']) 
    
    def mask_points(points,mask):
        p = np.array(points).T
        return p[mask,:].T.tolist()

    def mask_match(match,mask):    
        if np.sum(mask)==0:
            return None
        match['matches']['p']=mask_points(match['matches']['p'],mask)
        match['matches']['q']=mask_points(match['matches']['q'],mask)
        w = np.array(match['matches']['w'])
        match['matches']['w']=w[mask].tolist()
        return match

    def find_inside_points(r,stack,matchp,ts,poly):
        local_points=np.array(matchp).T
        world_points = r.run(renderapi.coordinate.local_to_world_coordinates_array,stack,local_points,ts.tileId,ts.z)
        worldPoints = [geometry.Point(x,y) for x,y in world_points]
        isInside = map(lambda x: x.within(poly),worldPoints)
        return np.array(isInside)

    def filter_match(r,match,stack,polyp,polyq,tsp,tsq):
        insidep = find_inside_points(r,stack,match['matches']['p'],tsp,polyp)
        insideq = find_inside_points(r,stack,match['matches']['q'],tsq,polyq)
        insideboth = insidep & insideq
        newmatch = mask_match(match,insideboth)
        return newmatch
        
    def filter_matches(r,stack,fromcollection,tocollection,polydict,pgroup):
        matches=r.run(renderapi.pointmatch.get_matches_with_group,fromcollection,pgroup)
        new_matches = []
        polyp = polydict[pgroup]
        z = r.run(renderapi.stack.get_z_value_for_section,stack,pgroup)
        tilespecs = r.run(renderapi.tilespec.get_tile_specs_from_z,stack,z)
        tiledict = {}
        for ts in tilespecs:
            tiledict[ts.tileId]=ts
        qgroups = set([match['qGroupId'] for match in matches])
        
        for qgroup in qgroups:
            z = r.run(renderapi.stack.get_z_value_for_section,stack,qgroup)
            tilespecs=r.run(renderapi.tilespec.get_tile_specs_from_z,stack,z)
            for ts in tilespecs:
                tiledict[ts.tileId]=ts
        for match in matches:
            qgroup = match['pGroupId']
            polyq = polydict[qgroup]
            new_match = filter_match(r,match,stack,polyp,polyq,tiledict[match['pId']],tiledict[match['qId']])
            if new_match is not None:
                new_matches.append(match)
        return r.run(renderapi.pointmatch.import_matches,tocollection,json.dumps(new_matches))

    def create_polydict(r,stack,mask_dir):
        sectionData=r.run(renderapi.stack.get_sectionData_for_stack,stack)
        sectionIds=[sd['sectionId'] for sd in sectionData]
        polydict = {}
        for sectionId in sectionIds:
            z = r.run(renderapi.stack.get_z_value_for_section,stack,sectionId)
            polyfile = os.path.join(mask_dir,'polygon_%05d.json'%z)
            polyjson = json.load(open(polyfile,'r'))
            poly = geometry.shape(polyjson['roi'])
            polydict[sectionId]=poly
        return polydict

    def create_zdict(r,stack):
        sectionData=r.run(renderapi.stack.get_sectionData_for_stack,stack)
        sectionIds=[sd['sectionId'] for sd in sectionData]
        zdict={}
        for sectionId in sectionIds:
            z = r.run(renderapi.stack.get_z_value_for_section,stack,sectionId) 
            zdict[sectionId]=z
        return zdict

    #define a dictionary of z values for each sectionId
    zdict = create_zdict(r,stack)
   
    #define a dictionary of polygons for each sectionId 
    polydict = create_polydict(r,stack,polygonfolder)
    
    #get the set of starting sectionIds for the point match database
    pgroups = r.run(renderapi.pointmatch.get_match_groupIds_from_only,matchcollection)

    #define a partial function on filter_matches that takes in a single sectionId
    mypartial=partial(filter_matches,r,stack,matchcollection,targetmatchcollection,polydict)
    
    #run function in parallel over 40 workers
    pool = mp.ProcessPool(4)  
    #res = pool.map(mypartial,pgroups)
    for pgroup in pgroups:
        mypartial(pgroup)