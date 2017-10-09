

node {
    stage 'check out'
         echo 'check out the git repository'
         git 'https://github.com/mindsoulpeace/hua-shan-lun-jian.git'
    stage 'run'
         echo 'run something'
         sh '''cd /workspace/fencer1/fence/
          python fencing.py --create=CREATE
          python fencing.py --askfred=ASKFRED --url=https://askfred.net/Results/results.php?tournament_id=35636'''
         echo 'run fencer db done'
    
}

